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

> **Status: §1 is BUILT (2026-09-20) — `software/boot/boot.asm` §10a, and
> `machine_tb`'s `disk` and `nodisk` scenarios read the picture off the
> connector. §2 and §3 are specified and nothing of them is built.**

---

## 0. The sequence, against what exists

| Mac 128K does | this machine | state |
|---|---|---|
| ROM finds the video hardware | `boot.asm`'s `vprobe` — writes `$A5`/`$5A` to `+$13` and reads back; video3 returns it, the archived card cannot (b2/b3 hardwired zero), an empty slot floats | ⭐ **built 2026-09-20** |
| clears the screen | the POST already paints all of 640 × 200 with the span writer | ⭐ built |
| a dialog, with an icon: *looking for a disk* | `boot.asm` §10a, drawn with the ROM toolbox | ⭐ **built 2026-09-20** — §1 |
| the icon changes when a disk is found | the same drawing path, and the Mac's blinking question mark when there is none | ⭐ **built 2026-09-20** — §1. ⚠ *found* means `SDSTAT` says a card is in the socket, not that it is bootable: §2 |
| loads the OS from the disk | `rbsd` reads the card **under NitrOS-9**; the ROM has no SD reader of its own, and the OS still boots from the ROM disk | ⛔ §2 |
| a desktop | `v3desk` is a **recording** | ⛔ §3 |
| a file manager | `v3trk` fills a Tracker window's list **from a real directory** | ⚠ §3 |
| an application menu | `v3menu` is a recording of one | ⛔ §3 |

---

## 1. The boot dialog — built

`boot.asm` §10a draws it, with the ROM toolbox (`tbox.asm`, ROM page `TB.Pg` = 64):
`Window` for the Haiku tab and frame, `Rect` for the desktop and the content panel,
`Icon` for the toolbox's own `disk`, `TextC` for the line beside it, `Pal` for the
256-entry Haiku palette. Three states, each with a progress code so a testbench can
say which was drawn:

| | | code |
|---|---|---|
| **looking for a disk** | drawn as soon as the palette is loaded and the screen is cleared | `$60` |
| **found** | `SDSTAT` b1 says a card is in the socket | `$61` |
| **no disk** | the Macintosh's blinking question mark, on the icon | `$62` |
| *no toolbox* | ⚠ page 64 is 8 KB of zeros in a build without `-DV3=1`, and in a bare `npm run rom`. The dialog is **skipped**, not half drawn | `$63` |

⛔ **It is the LAST thing the POST draws, not the first.** The Mac's order is probe,
clear, dialog; sections 3–10 of this ROM paint whole frames that `machine_tb` compares
pixel for pixel, so a dialog drawn before them would be painted over by every one of
them on the way past. So it comes after §10's VRAM read-back — which leaves it as the
picture the machine is holding when NitrOS-9 takes over, which is the Mac's behaviour
where it is visible.

### ⭐ It needed nothing added to `tbox`

The obstacle looked like the calling convention: `tbox`'s routines read `>CoG+…` and
want `Y` = `VG`, and at boot there is no CoArm and no `VG`. **A bare entry was not
needed.** `CoG` is `Co.Data` = **`$6000`, a logical address in CoArm's own map**, and
`Co.WinA` = `$A000`, `Co.WinB` = `$C000` ([`armvid.d`](../../nitros9/defs/armvid.d)).
The POST owns the whole map, so it reproduces that layout:

| logical | what the POST puts there |
|---|---|
| `$6000`–`$9FFF` (blocks 3–4) | SIMM, already — the `CoG` scratch. `TB` = `CoG + CG.LBuf` = `$8A4C` and `CG.TbV` = `$8F6F` are both in block 4 |
| `$A000` (block 5) | ROM page `TB.Pg` — the toolbox's code, where it expects to be running from |
| `$C000` (block 6) | the toolbox's **data** pages, as `tbox` switches them through `TV.MapB` |

and then calls it the way [`ca_tbox.asm`](../../nitros9/level2/arm6309/modules/ca_tbox.asm)
does: `ldd #$FF00+TB.Pg`, map it, `jsr >Co.WinA+3`, with `B` = the function, `X` = its
parameter block and `Y` = a **fabricated `VG`** — sixteen bytes of padding and `VG.Base`,
in ROM, because `VG.Base` is the only field anything on these paths reads.

**The `CoG` fields the POST sets, and why each one.** Everything else is unread on
these paths and is left alone:

| | |
|---|---|
| `CG.TbV` | the vector table `TVCALL` jumps through. Unset, the first rectangle jumps into whatever the SIMM holds |
| `CG.Dev` | `PN` answers `WT.Parms+1` off it — a call's parameter **byte count**, which is how `TStr` finds a string and its length. The POST's "window" is that one byte |
| `CG.OX`, `CG.OY` | `0, 0`, so a parameter **is** a screen coordinate |
| `CG.CX0`–`CG.CY1` | the clip, screen pixels, inclusive. `FillC` clamps to it and `BlitRow` drops a row outside it |
| `CG.WinB` | `$FFFF`. ⛔ `MapB` is a **compare**: a stale value that happens to match leaves the wrong ROM page in the window and says nothing |
| `CG.TTop` | `0` — the card's ring row of screen row 0, which `VSCROLL = 0` makes true |
| `CG.TStr` | `0`, "the card". The POST's row layer is card-only |

Left unset, and each provably unread: `CG.WinA` (only `MapA`, which `tbox` cannot call —
`Co.WinA` is its own code); `CG.Off` / `CG.DBlk` (`DSeek`/`DNext`, the DRAM-store back
end, which `CG.TStr = 0` never reaches); `CG.MFg` / `MBg` / `MTr` (`RowMask` and `Glyph`,
which have **no `TbVec` entry at all**, so no toolbox call can reach them); `CG.CurS`
(CoArm's palette entries want a screen record; the POST's do not); `CG.RX`/`RY`/`RN`/`FH`
(written by `tbox` itself before every call out).

### What the POST had to write instead

`TbVec` — CoArm's row layer, for a machine with no CoArm in it. Seven entries, of which
`tbox` reaches five: `TV.Rect` (span-solid, in chunks of 256 with a bounded `SPANBUSY`
poll before each), `TV.Put` (`WMODE` 00 direct through `VDATA`, no poll between bytes —
`/WAIT` is what holds the CPU off), `TV.MapB`, `TV.PalSet` (`PIDXL`/`PIDXH` written for
**every** entry, which is §3's rule and the reason for it), and `TV.PalShw`, which has
nothing left to do because `TV.PalSet` wrote the card's LUT directly.

⛔ **And the stack moves.** `Co.WinB` is `$C000` and `lds #STACK` put `S` at `$E000`,
descending into block 6 — so for the length of the dialog the stack, and §10a's own
variables, live in block 0. The POST's other variables at `$C010`–`$C01B` go under the
data page too; they are SIMM bytes that the remap only *hides*. ⚠ This is also why
§10a does not call `settle`: `settle` counts frames in `nfrm`, which is in block 6, so
it would store a count into a ROM page and loop until a byte of a font happened to be 1.

⚠ **`boot.asm` has a second copy of `armvid.d`'s offsets and cannot have anything else**
— A09 cannot include lwasm source. [`checkcg.py`](../software/nitros9/tools/checkcg.py)
re-derives all 22 with lwasm off the real `armvid.d` and `software/nitros9/mkrom.sh`
refuses to build a ROM whose two halves disagree.

**Cost: two ROM pages mapped for the length of the dialog, ~790 bytes of ROM, eight
bytes of variables and a stack in block 0 — plus `CoG`'s scratch and `tbox`'s own
`TB`, which are SIMM the POST was not using.**

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

⭐ **And §1's `bootchk` is the hook.** It is a label in `boot.asm` between the
card-detect test and the *found* picture, with both pictures already drawn either side
of it: §9.0's power-up, §9.1's `CMD17`, `CMD58`'s `CCS` and block 0's signature go
there, and the branch each answer takes is already written. Until then *found* means
only "`SDSTAT` b1 says a card is in the socket" and the ROM disk is still the boot
device either way.

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
| the boot dialog | §1 — **built**: ~790 bytes of POST, of which about half is the row layer `tbox` draws through, calling a toolbox that was already there |
| a minimal SD reader | §2 — ~400 bytes, and it is the only way the card can become the boot device |
| ⛔ ~~`tbox`'s bare entry~~ | §1 — **not needed and not written.** The POST reproduces CoArm's map instead, and the toolbox is byte for byte what it was |

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
