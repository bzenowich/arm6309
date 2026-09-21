# From Reset to a Desktop

## A Macintosh 128K Boot, and What This Machine Already Has For It

**Question this answers:** the owner wants the machine to boot the way a Mac 128K does —
ROM finds the video card, clears the screen, puts up a dialog with an icon saying it is
looking for a disk, changes the icon when it finds a bootable one, loads the operating
system off the SD card, and comes up on a desktop with a working file manager and an
application menu. **What is already built, what is a mock-up, and what is missing?**

**Short answer: the drawing was always real, the boot half is done, and the
desktop stopped being a recording on 2026-09-20.** `v3desk`, `v3paint` and `v3menu` are
scripted streams of CoArm escape sequences, played with `copy /sd0/data/v3desk /w3`, that
paint a *picture* of a desktop; they are still on the card and are still what the demo
session shows. `desk` is the program that emits those escapes **live, off the mouse** —
§3 — and since 2026-09-21 it has a file manager that lists, enters and runs what is
really on the card. What is left is windows that move and close.

> **Status: §1 is BUILT (2026-09-20) — `software/boot/boot.asm` §10a, and
> `machine_tb`'s `disk` and `nodisk` scenarios read the picture off the
> connector. §3's MILESTONES 1 AND 2 ARE BUILT (2026-09-20) — `desk`, a
> NitrOS-9 command on the SD card, and `video3/bench/run-v3desk.sh` clicks at
> it with a `PS2_SCRIPT` and reads the answers off the frames. ⭐ **§3's
> MILESTONE 3 IS BUILT (2026-09-21)** — the file manager, and with it the
> desktop icons that §5 item 6 said were drawn and dead;
> `video3/bench/run-v3files.sh` reads the listing off the pixels and compares
> it with the host's `os9 dir`. ⭐ **§2 IS BUILT (2026-09-21)** — the machine
> reads the card before there is an OS (`boot.asm` §10b) and NitrOS-9's
> `boot_sd` loads `OS9Boot` off it, with the ROM disk as the fallback;
> `software/nitros9/run-sdboot.sh` boots all three card states from reset.
> §3's milestone 4 is specified and not built.**

---

## 0. The sequence, against what exists

| Mac 128K does | this machine | state |
|---|---|---|
| ROM finds the video hardware | `boot.asm`'s `vprobe` — writes `$A5`/`$5A` to `+$13` and reads back; video3 returns it, the archived card cannot (b2/b3 hardwired zero), an empty slot floats | ⭐ **built 2026-09-20** |
| clears the screen | the POST already paints all of 640 × 200 with the span writer | ⭐ built |
| a dialog, with an icon: *looking for a disk* | `boot.asm` §10a, drawn with the ROM toolbox | ⭐ **built 2026-09-20** — §1 |
| the icon changes when a disk is found | the same drawing path, and the Mac's blinking question mark when there is none | ⭐ **built 2026-09-20** — §1. ⭐ *found* means a card the ROM has read a boot signature off since 2026-09-21: §2 |
| loads the OS from the disk | `boot.asm` §10b reads block 0 before there is an OS; `boot_sd` reads `OS9Boot` off the card, and the ROM disk is the fallback | ⭐ **built 2026-09-21** — §2, `sdcard.md` §9.5 |
| a desktop | `desk` — a menu bar, an event loop on the PS/2 mouse, icons on the Haiku desktop | ⭐ **built 2026-09-20** — §3 milestone 1. ⭐ The icons became clickable 2026-09-21 |
| a file manager | `desk`'s Tracker window, listing a real directory through `v3dir.inc` — the reader `v3trk` has always used | ⭐ **built 2026-09-21** — §3 milestone 3 |
| an application menu | `desk`'s **Applications** menu forks `v3paint`, `monster` and `pinball` off `/SD0/CMDS` | ⭐ **built 2026-09-20** — §3 milestone 2 |

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
| **found** | ⭐ **since 2026-09-21**: §10b initialised the card, `CMD58` reported `CCS`, and block 0 carries `sdcard.md` §9.5's signature over a non-zero `DD.BT`. The verdict is written first, as `$64` | `$61` |
| **no disk** | the Macintosh's blinking question mark, on the icon. ⭐ Reached two ways, and the codes above it say which: an empty socket, or **a card that is there and is not bootable** (`$65`) — which is the Mac's actual question mark | `$62` |
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

⭐ **Built 2026-09-21.** `OS9Boot` comes off the SD card when there is a bootable one in
the socket, and off the ROM disk when there is not. `storage/docs/sdcard.md` §9.5 is the
design; this is what it is made of and what it changed here.

**Two readers, because there are two moments.** The boot ROM has to read the card before
there is an OS; the kernel's `F$Boot` module has to read it again once there is.

| | |
|---|---|
| `boot.asm` **§10b** | the ROM's reader: §9.0's initialisation and §9.1's `CMD17` of block 0, ~640 bytes. No filesystem, no directory walk, no write path, **no block buffer** — the eight bytes the verdict needs are picked out of the 512 as they go by. ⚠ It never loads anything. Its whole output is which of §1's three pictures is true |
| `boot_sd.asm` | the NitrOS-9 `F$Boot` module (nitros9 `level2/arm6309/modules/`), 881 bytes of the loader's 896: `HWInit`/`HWTerm`/`HWRead` for `boot_common.asm`, which is `boot_romdisk`'s ROM-page reader with the card in front of it. It reads `OS9Boot` and, when it cannot, falls back to the ROM disk in the same call |

**Where `OS9Boot` lives: a contiguous run named by `DD.BT` and `DD.BSZ` in LSN 0** — which
is the first half of SD block 0. Of the two options this section used to offer, that is
the fixed block range, and it needed no new structure invented: `RBF`'s own volume header
already carries the pair, `os9 gen` already writes it, and NitrOS-9's `boot_common.asm`
already reads it. The path-and-directory-walk alternative would have cost the ROM ~300
bytes it does not have and the kernel the same code twice. **`software/nitros9/mksddisk.sh`
`BOOT=<bootfile>` is what makes a card bootable**, and what stamps LSN 0 `+$F0` with the
signature `"6309"` — the same four bytes §11 of the ROM looks for at `$8000`.

⭐ **And §1's `bootchk` is no longer a hook.** *Found* now means a card that answered
`CMD58` with `CCS` **and** whose block 0 carries that signature over a non-zero `DD.BT`,
so the third picture is the Macintosh's real one: **there is a disk in the drive and it is
not a system disk.** The old test — `SDSTAT` b1, the socket's mechanical switch — could not
tell those two apart at all, and drew *Disk found* over a blank card.

⛔ **The ROM disk stays bootable, and that is the point.** It is this machine's rescue
system: `format`, `dcheck`, `copy` and `makdir` are on it so that a blank card can be
brought up from nothing, and a boot that refused to happen because the card was bad would
take the tool for fixing the card with it. So the precedence is **card first, ROM disk
always**, and a bench asks for the ROM disk by not putting a bootable card in the socket —
which is what every bench written before this already does. `BOOTMOD=boot_romdisk` builds
the ROM that cannot read a card at all.

⚠ **`/DD` does not move.** Only `OS9Boot` came off the card; the system disk is still the
ROM disk and `/SD0` is still mounted beside it by `rbsd`.

⭐ **And it says which one it used**: `boot_sd` prints one character through `D.BtBug`,
between `krn`'s `tb` and `boot_common`'s `0` — **`s`** for the card, **`r`** for the ROM
disk. ⛔ Without it, *"a shell appeared"* is evidence of nothing, because the fallback
works: a machine that silently ignored the card reaches exactly the same prompt.
`software/nitros9/run-sdboot.sh` (**45 claims**) is the bench, and it asserts the same
thing a second, independent way — the card carries a **different** `OS9Boot`, with two
extra modules in it, so `mdir` names them only on a machine that read the card.

---

## 3. The desktop, which is the whole job

⭐ **The event loop, the menu bar and the launcher are built** (2026-09-20):
[`desk.asm`](../../nitros9/level2/arm6309/cmds/desk.asm), a NitrOS-9 command on the SD
card beside the demos it launches. It is an application, not ROM — §4 — and its own
header is the detailed design. `video3/bench/run-v3desk.sh` is the bench.

⚠ **The recordings are still there and are still a recording.**
`copy /sd0/data/v3desk /w3` draws a Tracker window, a Deskbar and a fuller desktop than
`desk` does, and none of it is clickable. They are the *picture* the shell is being grown
towards, and `v3show.py` remains where that picture is authored.

**The pieces this was assembled out of, all of which already existed:**

| piece | what it does for the shell |
|---|---|
| `tbox` | every rectangle, bevel, icon and string `desk` draws is an `ESC $6A` call into the ROM toolbox. **There is no drawing code in `desk` at all** — only escape bytes and hit testing |
| CoArm | the windows, the screens, `/W1`–`/W5`, `SS.Excl`, and `SS.Mouse`, which `armio.asm` answers out of the `Pt.*` packet `ca_ptr.asm` builds in `VG.MsPkt` |
| PS/2 mouse | `kbdarm.asm`'s IRQ service keeps `VG.MsX`/`VG.MsY`/`VG.MsBtn`; `desk` polls them through `SS.Mouse` and never touches the hardware |
| `F$Fork` | the launcher. The demos are at `/SD0/CMDS` and a bench's `chx /sd0/cmds` is what puts them on the execution path |
| `v3trk` | ⭐ **the directory reader, shared at source.** `v3trk`'s read loop is `modules/v3dir.inc` since 2026-09-21 and `desk` includes the same file — §3.6 |
| `v3drag` | **still unused by the shell** — it is milestone 4's window move |

### 3.1 The event loop

One pass a system tick (`F$Sleep 1` — the tick *is* the card's vertical blank), and every
pass is bounded work: the keyboard **non-blocking** (`SS.Ready` first, `I$Read` one byte
only if it says there is one), then `SS.Mouse`, then a state machine of two states and
four edges —

| state | event | what happens |
|---|---|---|
| idle | a button **press** in the bar over a title | that menu comes down |
| open | motion | the highlight moves to the item the pointer is over |
| open | a **press** on an enabled item | dismiss, then act |
| open | a **press** anywhere else | dismiss |

⚠ **A press is an EDGE, not a level.** The button is sampled every tick and acted on only
where this tick has it down and the last did not; a click is ~50 ms and would otherwise be
three presses. `Pt.Valid = 0` — our window is not the selected one — *resets* the edge
detector rather than being ignored, so the first press after a launch is a fresh one.

⚠ **And the loop carries an iteration bound**, which is the discipline `CLAUDE.md` asks of
every wait in this repository: a desktop that has lost its window stops rather than
spinning. It is not a timeout on anything inside the loop.

⛔ **Echo is turned off** (`SS.Opt`, `PD.EKO = 0`) before the first read. SCF echoes what
`I$Read` takes, and the echo would be drawn **on the desktop** by the console's own
put-character.

### 3.2 The menu bar, and what the bench reads

Two titles — **Desk** (About, Quit) and **Applications** (Paint, Monsterland, Pinball
and Stardew) — in an 18-pixel bar of `C.ITab` with one row of `C.Frame` under it.
A pull-down is a `tbox` bevel; an item is highlighted by repainting its rectangle in
`C.Sel` and its label in the `sel` ramp, and unhighlighted by repainting it in `C.Panel`.

⭐ **A greyed item is refused the highlight as well as the action**, so hovering it says so
too — the mechanism is `A.Dis` and it is what carried `Stardew` while it was specified and
not built. ⭐ **All four items are live since 2026-09-21**, when
[`video3/docs/stardew.md`](../video3/docs/stardew.md)'s farm was built; `history.md` has
what the greyed entry was for.

⭐ **Dismissal repaints rather than saving pixels.** The rectangle the pull-down covered is
filled with the desktop colour and every desktop icon is drawn again — `desk` holds its own
display list and never reads the card back. The two Applications items sit **over two of
the icons on purpose**, so "dismissing restores what was underneath" is a claim about
something rather than about flat blue: `run-v3desk.sh` compares the rectangle's CRC with
the one it had before the menu existed.

### 3.3 The launcher, and the exclusive screen

⭐ **This is §5 item 4's answer, and what decides it is not `SS.Excl`.** It is that
`ca_scr.asm`'s `DoDWSet` answers `E$WADef` to a **second** `DWSet` on a window that is
already defined. So a child cannot make itself a screen on a device whose window the
desktop is still holding, and the desktop cannot keep its window across a launch. It
therefore gives it up:

| | |
|---|---|
| 1 | **`DWEnd`.** `DevEnd` drops the desktop's window, `ScrFree` frees its 640 × 480 store and `CG.Disp` goes to 0. The desktop's picture is gone, and `desk`'s own display list is the only copy that matters |
| 2 | the child is forked with a **duplicate of the window path** as its standard output (`I$Dup`), so its own `DWSet` lands on the same device — and so the keyboard and the mouse, which CoArm routes by `VG.CSel` to the **selected window's device**, keep pointing at the device the desktop will take back |
| 3 | the child takes `SS.Excl` on **its** screen and owns the card. The desktop is asleep in **`F$Wait`**: it polls nothing, draws nothing, and cannot race the exclusive owner for `VG.CBusy` |
| 4 | the child exits. ⭐ **The claim comes back twice over** and neither way needs the app to be well behaved: `vidxcl.asm`'s `XCheck` releases a screen whose owner process is gone, and the `DWEnd` the desktop does next reaches `ScrFree`, which calls `XRelease` for the screen it frees |
| 5 | `DWEnd`, `DWSet`, `Select`, repaint. The desktop trusts nothing that was left on the card |

⚠ **`PutGC` is issued once, at start-up, and never again.** It does not move the pointer,
it moves the **mouse** (`ca_ptr.asm`'s `DoPutGC` writes `VG.MsX`/`VG.MsY`), and the mouse is
relative — so a `PutGC` after a launch would silently teleport the user's hand. `GCSet` is
re-issued every time, because `SS.Excl` saved `VG.PtrOn` and `XRelease` put back whatever
the child left.

⚠ **The consequence a bench has to know about: while a child runs, the desktop is deaf.**
`v3paint` takes ~45 s of machine time from the click to the desktop's repaint, and a click
sent inside that window reaches nobody. `run-v3desk.sh` states that as a claim
(`deskback < C4.t`) rather than leaving a mistimed script to fail somewhere else.

### 3.4 `v3paint`, and why a menu item cannot fork a stream

`v3paint` was a *data file*; the menu needs a *program*. So
[`v3paint.asm`](../../nitros9/level2/arm6309/cmds/v3paint.asm) is the smallest honest one:
it opens `/SD0/DATA/v3paint`, sends it to its own standard output, and holds the picture up.
The stream's own first escapes are `DWSet $13`, `Select` and `Pal`, so the program knows
nothing about the card, the toolbox or the palette.

### 3.5 What is left

3. **The file manager (built 2026-09-21; §3.6).**
4. **Windows that move and close** — `v3drag` already moves one with the copy engine. A
   second manager window needs that first: two windows with no clipping is whichever was
   drawn last (`v3show.py`'s `stream_cmds` says so), so the move has to come before the
   second window does. Rename, copy and delete after.

### 3.6 The file manager — built

⭐ **A Tracker window on the desktop, listing a real directory**, opened from the **Go**
menu (`Files`, `Up`, `Open`, `Close`) or by clicking the desktop's disk icon.
`video3/bench/run-v3files.sh` is the bench.

**The model is a table and four bytes**, in `desk`'s own data area, and nothing is ever
read back off the card:

| | |
|---|---|
| `ftbl` | `FM.MAX` = 48 records of 32 bytes: kind, length, the name, a NUL |
| `fcwd` | the directory the table came from, NUL-terminated, 64 bytes |
| `fn` `ftop` `fsel` | how many entries, the first row showing, the entry selected (or `$FF`) |

⭐ **That is why the window survives a launch.** §3.3's handover ends in `DWEnd`, `DWSet`,
`Select` and `DrawAll`, and `DrawAll` now redraws the manager out of `ftbl` — the child's
screen took the pixels and could not take the model.

⭐ **The reader is `modules/v3dir.inc`, not a second one.** `v3trk` has read a real
directory since 2026-09-17; its loop moved into an include on 2026-09-21 and both programs
use it. `DirOpen`, `DirNext`, `DirClose`, registers only, no data-area convention — the
same trade `v3lib.inc`'s header argues, for the same reason (a subroutine module costs an
8 KB block of a 64 KB process map).

⛔ **What makes something a directory is RBF's answer, not the name.** `DirOpen` asks for
`DIR.+READ.` and [`rbf.asm`](../../nitros9/level2/modules/rbf.asm)'s attribute check ORs
`DIR.` into the access the caller asked for and ANDs `FD.ATT` before comparing — so
`DIR.+READ.` on a file answers `E$FNA`, and plain `READ.` on a directory does too. Opening
an entry is therefore: try it as a directory, and if RBF refuses, fork it. The
no-lower-case convention picks the **icon** and `OpenEnt` corrects the record when the open
disagrees with it.

⭐ **A click selects; a click on the selection opens.** A double-click therefore opens, and
so does select-look-open, and **neither needs the loop to measure time** — which it cannot
do honestly, because a pass is `F$Sleep 1` plus whatever drawing the last event asked for.
The same rule governs the desktop icons (§5 item 6).

⚠ **A click that lands while the manager is redrawing is lost.** The loop samples the
button once a pass and a pass that repaints twelve rows is **2.09 s**, so a 120 ms click
inside one never produces an edge. This is not slowness, it is a polled loop with no
latched button: `ca_ptr.asm`'s packet carries the button's **level**, and nothing between
the IRQ and `SS.Mouse` remembers that it went down and up again. `run-v3files.sh` found it
by clicking a scroll arrow three times a second apart and moving the list one row; the
bench leaves 4.5 s between clicks and says why. **Fixing it belongs in the driver** —
a sticky "was pressed" bit in `VG.MsBtn` that `SS.Mouse` clears on read. Item 7 is the
number; item 8 is what the repaint is made of.

⭐ **The repaint is timed by the program itself.** `desk` stores `$50`–`$55` to `$FF2E`,
which decodes nowhere on the board and which the host emulator timestamps into
`marks.txt` in picoseconds (`software/demo/demo.asm`'s `MARK`, `monster`'s instrument):
`DrawFiles` begins and ends, `DrawList` begins, and each row's `Rect`, `Icon` and name are
bracketed. Three stores a repaint and three a row — 39 of them, about 0.2 ms of 2,085 —
and they are **inside** every number the two items below quote.

⚠ **The window title is clipped at 55 characters.** `ca_tbox.asm`'s `DoTbCall` refuses a
call of more than 64 parameter bytes (`WT.Poly` is 64) and a `Window` call is the title
plus nine; a deeper path is drawn short rather than not drawn. `OpenEnt` separately refuses
to enter a path longer than 62, because `fcwd` is 64 bytes.

⚠ **The execution directory follows the list.** `F$Fork` takes a module *name* and finds it
through the execution directory, so `OpenEnt` issues `I$ChgDir EXEC.` on `fcwd` before it
forks. The Applications menu forks bare names too and inherits wherever the manager last
went; on this card everything forkable is in `/SD0/CMDS`, so the two agree.

⚠ **The table holds 48 and the twelfth row is the last one showing.** A directory with
more than `FM.MAX` entries is listed to 48 and the status strip says `48+ items`; the rest
are neither drawn nor reachable. That is a cap and not a paging scheme, and the bench's
`DATA` is deliberately a curated twenty so the two questions stay apart.

⭐ **What the bench establishes**, all of it off the card's own output: the chrome where
`FM.*` says, the active tab, the title and the count as *text*, the listing as text
against the host's `os9 dir`, one click selecting and a second entering, both scroll
arrows, `Go > Up` and `Go > Close`, a desktop icon opening the manager, and `v3paint`
forked from a list row and the window still there afterwards — **65 claims**, with a
control that walks the list and presses nothing.


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
2. **Where `OS9Boot` lives on the card (answered 2026-09-21; §2, `sdcard.md` §9.5).** The
   fixed block range, and it is `RBF`'s own `DD.BT`/`DD.BSZ` in LSN 0 — no new structure,
   and `boot_common.asm` already reads it. The signature at LSN 0 `+$F0` is what says the
   volume was blessed for this machine.
3. **Whether the ROM disk stays bootable (answered 2026-09-21; §2).** It does, and the
   precedence is card first, ROM disk always — the fallback is inside `boot_sd`, so there
   is no configuration in which the machine will not start. ⚠ What is **not** answered is
   whether `/DD` should follow `OS9Boot` onto the card; today it does not, and the card is
   `/SD0` beside a ROM disk that is still the system disk.
4. **The mouse under an exclusive-screen program (answered 2026-09-20; §3.3).** The
   desktop gives its window up with `DWEnd` before it forks and sleeps in `F$Wait` while
   the child has the card. ⚠ **What is still open is the part nobody wants**: for the ~45 s
   a child owns the screen the desktop is deaf, and there is no way to leave it — no
   command key, no force-quit, and no second screen to switch back to. A shell that cannot
   interrupt what it launched is a shell with one application.
   ⛔ **And the floor is not the child's run time — it is ~26 s, measured 2026-09-21.**
   `video3/bench/run-v3desk.sh` clicks Stardew on a card that carries the module and not
   its world, so the scene gets as far as reporting the missing file and exits; the
   recording still shows the card on the child's 640 × 400 screen from **96.2 s to
   114.4 s**, and the desktop takes no click before then. The child's `DWSet`, the
   desktop's `DWSet` back and its whole `DrawAll` all go through CoArm's toolbox escapes,
   which is where the time is. ⚠ The bench's mouse script waits that out with an absolute
   `at`, and a relative delay there is a Quit that is never seen.
5. **The desktop's four applications all launch (answered 2026-09-21; §3.2).** `stardew`
   was the last greyed item; its scene is built
   ([`video3/docs/stardew.md`](../video3/docs/stardew.md), and
   `video3/bench/run-v3star.sh`) and the item is `A.Run` like the other three. ⚠ What is
   still true is that `stardew` needs its 491,520-byte world on the card, so a card built
   without `stardew.pic` launches it and gets its error page.
6. ⭐ **The desktop icons (answered 2026-09-21; §3.6).** `IcTab` carries an action and an
   argument per icon and `IconAt` hit-tests the
   64 × 48 cell: a click selects (the icon's dark variant, its label in the selection
   ramp), a click on the selection acts. The disk and Tracker icons open the file manager
   on `/SD0`; `Paint` forks what the menu item forks; `Zelda`, `home` and `Trash` select
   and do nothing, because there is nothing for them to do yet.
7. ⚠ **A click that arrives while the shell is drawing is lost** (§3.6), and since
   2026-09-21 the window it is lost in is a measured **2.09 s** rather than "seconds".
   The event loop polls the button's level once a pass; nothing latches the edge.

   ⭐ **What survives, measured.** Six clicks on the file manager's scroll arrows at one
   interval, counted by the repaints they cause (`$52` marks):

   | clicks 6 apart by | before item 8 | after |
   |---|---|---|
   | 3.0 s | 6 of 6 | 6 of 6 |
   | 2.6 s | 6 of 6 | 6 of 6 |
   | **2.2 s** | **3 of 6** | **6 of 6** |
   | **2.0 s** | 3 of 6 | **3 of 6** |
   | 1.5 s | 3 of 6 | 3 of 6 |
   | 1.0 s | 2 of 6 | 2 of 6 |
   | 0.5 s | 1 of 6 | 2 of 6 |

   ⛔ **So item 8's flag improves this and does not close it.** The threshold is the
   repaint, exactly: it moved from between 2.2 and 2.6 s to between 2.0 and 2.2 s because
   `DrawList` moved from 2.57 s to 2.09 s. **A person clicking a scroll arrow three times
   a second loses two clicks in three, before and after.** Closing it needs the driver —
   a sticky "was pressed" bit in `VG.MsBtn` that `SS.Mouse` clears on read, in
   `ca_ptr.asm` — and that is still not written. ⚠ Making the draw fast enough instead
   would mean a repaint under ~150 ms, which is **fourteen times** what item 8's next
   step is worth on its own arithmetic.

   ⚠ `run-v3files.sh` keeps its 4.5 s between clicks. Two seconds of margin over a
   threshold that is itself the draw time is what stops a bench failing because a row's
   name got one glyph longer.

8. ⛔ **THE TOOLBOX DOES NOT USE THE COPY ENGINE, AND THE KEYED COPYRECT WAS BUILT FOR
   THIS** — opened 2026-09-21.

   `tbox.asm` contains no `CPTR`/`CCTRL` reference at all. Every icon and every glyph is
   drawn by scanning each row for runs of non-transparent pixels and issuing one `RowPut`
   per run — its own header counts *"~395 of them"* for one transparent glyph. Meanwhile
   [`video3/docs/keyed-copy.md`](../video3/docs/keyed-copy.md) describes a copy that skips
   a source byte of zero in hardware, at the engine's 0.247 µs a byte, and §6.3 of it
   names a windowing GUI as the case it exists for. The demos use it (`v3lib.inc`), the
   driver uses it (`vidcpy3.asm`), `v3drag` moves a whole window with it — and the thing
   that draws the windows does not.

   ⛔ **And the two mechanisms do not use the same key**, which is the first thing anyone
   trying this will hit:

   | | transparent index |
   |---|---|
   | the card's keyed copy | **0**, fixed in `v3lane` — the comparator a key *register* would need is a DIP-20 and the board had room for a DIP-14 |
   | `tbox`'s software transparency | **15** — `KEY equ 15, never drawn: a transparent pixel` |

   Index 0 is black in the toolbox's palette and 15 is the magenta key, so the ROM's art
   cannot be handed to the engine as it stands. Renumbering reaches `mktbox.py`,
   `v3show.py`, `tbox.asm`'s equates and the ROM data itself.

   ⚠ **Window titles are the WORST candidate, not the best.** `tbox` keeps a ramp per
   background — `R_PANEL` on grey, `R_WHITE` on white — precisely because the
   anti-aliased levels *bake the background in*. A keyed copy is binary: it writes a byte
   or it does not, and cannot blend, so a glyph keyed onto a background it was not
   rendered for shows its fringe. Text stays where it is until something renders glyphs
   per background, which is a different feature.

   ⭐ **The prize is item 7's repaint**, and since 2026-09-21 it is a number rather than
   an argument. `desk` marks its own drawing at `$FF2E` (§3.6) and the file manager's
   twelve rows cost this, on `/SD0/DATA`'s twenty entries with six- to eight-character
   names:

   | | transparent text | **opaque text** | |
   |---|---|---|---|
   | a row's `Rect` (404 × 18, the span writer) | 18.3 ms | 18.3 ms | — |
   | a row's **icon** (16 × 16, run scanned) | 47.2 ms | 47.2 ms | — |
   | a row's **name** | 109.5 ms | **71.4 ms** | −34.8 % |
   | **one row** | 175.0 ms | **136.9 ms** | −21.8 % |
   | **`DrawList`** — 12 rows, the scroll bar, the count | **2,565.7 ms** | **2,085.4 ms** | −18.7 % |
   | **`DrawFiles`** — that plus the window, the tab and the header | **3,437.0 ms** | **2,956.8 ms** | −14.0 % |

   ⭐⭐ **STEP ONE IS DONE AND IT WAS `F.Opaq`, NOT THE COPY ENGINE.** `desk.asm` never
   set it, so every list row took `tbox`'s **transparent** path: the `KEY` fill, the run
   scan, and one `RowPut` per run — the ~395-calls-per-40-character-line figure that
   `run-v3text.sh` measured at 41 % of the bill. `F.Opaq` is the toolbox's own answer and
   had been there all along: the glyph writes the ramp's own paper, so **a row is ONE
   run**. It is "pre-render the text against the background it will sit on", done in
   software — no glyph bank, no VRAM upload, no palette renumbering, no engine.

   ⛔ **It is set where the background is uniform, known, AND is that ramp's paper** —
   two call sites, the list's rows (`R.White` on `C.White`, `R.Sel` on `C.Sel`) and a
   pull-down's items (`R.Panel`/`R.Dim` on `C.Panel`, `R.Sel` on `C.Sel`). The pixels
   there are unchanged, because level 0 of the glyph now writes the byte the `Rect`
   underneath had already written.

   ⚠ **Four call sites are deliberately left transparent, and three of them for one
   pixel.** The font is **17 rows** and `tbox` paints the whole line box, so an opaque
   line needs 17 rows of its own to land in:

   | | why not |
   |---|---|
   | the desktop icons' labels | they sit on the **wallpaper**, and a selected one is drawn in the selection ramp over it. This is the case the flag would be visible in |
   | the manager's column header | `FM.HH` is 17, so a box at `+1` runs to row 17 of a bevel whose rows are 0–16: it would take the bevel's own bottom shadow and bleed a row into the list |
   | its status strip | `FM.SH` is 17. The same pixel |
   | the menu bar's titles | `GEO.TITY` is 2, so the box ends on row 18 — which is `GEO.RULEY`, the `C.Frame` rule under the bar |

   Together they are four calls against the list's twelve, so the cost of refusing them is
   small; giving the header and the strip one more row each would recover it, and that is
   a geometry change the benches read, not a flag.

   ⛔ **IT DID NOT CLOSE ITEM 7 — see the table there.** The threshold for a click
   surviving moved from 2.6 s to 2.2 s, which is exactly `DrawList`. **What is left is not
   the text.** Of the 137 ms a row now costs, **47 ms is the 16 × 16 icon** — 565 ms of
   every repaint, 27 % of it, drawn by scanning each row for runs. That is the irregular,
   fixed-size, per-row shape the keyed copy exists for, and it is now the largest single
   item that is not already the span writer.

   ⛔ **And the arithmetic still says a per-glyph blit would be SLOWER than `F.Opaq`.** A
   copy costs ~87 µs of setup whatever its size (`monster`'s measurement), so a
   40-character title as 40 glyph copies is ~3.5 ms — against one opaque line. **The
   engine wins on big rectangles and loses on small ones**; a 12 px glyph is the wrong
   shape for it. A 16 × 16 icon at one copy each is 12 × 87 µs = ~1 ms a repaint against
   565 ms, which is the case for doing the icons and not the type.

   ⚠ **Two sizing notes** for whoever does build a bank: an OS-9 listing is **mixed case**
   — `OS9Boot` sits beside `CMDS` and `DATA` — so a body alphabet is ~70 glyphs and not
   64; and the bank must live in **VRAM**, because the copy engine is VRAM-to-VRAM, which
   is a start-up upload the software path does not need.

   ### What the early Macintosh did, and which of it is left to take

   Asked 2026-09-21: *what did the early Macs do to draw proportional text quickly, and
   what can this borrow?* The answer turns out to be mostly **"`tbox` already does it"**,
   and the two pieces it does not do are worth different amounts. ⚠ The figures below
   marked *estimated* are cycle counts read off the source at E = 2.0979 MHz, not
   measurements; the last paragraph says which measurement settles them.

   | the Mac's technique | `tbox` | |
   |---|---|---|
   | **compose the string into a buffer, then move it** — `DrawText` built a line and blitted it, rather than going to the screen per glyph | ⭐ **already done.** `TextAt` fills `TB.Buf` with the paper, walks the string laying each glyph's row in at `TB.CX`, and calls `BlitRow` once | — |
   | **the strike**: every glyph of a face packed side by side in one wide bitmap, with a location table whose *differences* are the widths | partly. The font has a 3-byte directory entry per glyph (width, 2-byte offset) and `Glyph` reads it — ⛔ but **once per glyph per row**, so a 17-row line does the lookup and a `mul` for the row offset seventeen times over | ⚠ ~4 ms of 71, **estimated** |
   | **the source layout is the destination layout**, so a row is a shift-and-mask of whole words with no per-pixel work | ⛔ **and this one is already paid for.** The font is 2 bits a pixel and the screen is 8, so `GRow` must expand — but `TB.NTab` makes a nibble **two destination bytes in one `ldd`/`std`**, which is the same two-pixels-an-instruction a pre-expanded font would achieve | ⛔ **nothing**, see below |
   | **synthesized styles** — bold as the glyph OR'd with itself shifted one pixel, italic as a per-row shear | not done: `F.Bold` selects a **second font** and `FontMap` maps its page | saves ROM, not time |
   | **the system font resident in ROM** | ⭐ already: the fonts are ROM pages, mapped at `Co.WinB` by `FontMap` | — |

   ⛔ **THE CACHE-OF-EXPANDED-GLYPHS IDEA IS DEAD, AND `TB.NTab` IS WHY.** The obvious
   borrow — "pre-expand each glyph to destination bytes for its ramp, so drawing is a
   copy" — assumes the expansion is the cost. It is not: a nibble is one table index and
   one `std`, which is **two pixels an instruction**, and a `memcpy` of pre-expanded
   bytes is also two pixels an instruction. The bank would cost ~275 KB across three
   ramps, or a VRAM upload at start-up, **to run the same speed**. The 32-byte table in
   RAM already bought the win; it is dated in `tbox.asm` at *"~45 cycles a pixel"* saved.

   ⭐ **AND THE ARITHMETIC SAYS THE GLYPH LOOP IS NOT THE BILL AT ALL.** A seven-character
   name is ~50 px wide and 17 rows. ⚠ **Estimated**, from the source:

   | | |
   |---|---|
   | the paper fill — 50 bytes a row, 2 at a time, × 17 | ~2.4 ms |
   | `GRow` — 850 pixels at ~10 cycles | ~4.1 ms |
   | `Glyph` + the row-offset `mul`, ⛔ **× 17 rows** | ~3.9 ms |
   | **all the pixel work** | **~10 ms** |
   | **measured, the whole name** | **71.4 ms** |

   ⛔ **So ~60 ms of the 71 is not glyphs.** What is left in the loop is **seventeen
   `BlitRow`s and seventeen `FontAgain`s** — one transfer and one page remap per row,
   each of them a `TVCALL` into CoArm and back. The Mac's *"blit the line once"* is
   therefore the one technique here with real money behind it, and ⚠ **it is not about
   the card**: `F.Opaq` already made each row a single `RowPut`, so the seventeen
   `RowPut`s are as few as a row-at-a-time design can make them. The saving would have to
   come from **moving the row loop to the far side of one call** — `BlitBox`, a 17-row
   `TB.Buf` handed over once — not from a different way of drawing a glyph.

   ⚠ **THE MEASUREMENT THAT SETTLES IT, AND NOTHING SHOULD BE BUILT BEFORE IT.** The
   ~60 ms above is a subtraction, not an observation, and subtractions are how the last
   two of these went wrong — item 8's own text predicted the glyphs and the icon turned
   out to be 27 %. `desk` marks its drawing at `$FF2E` already; marking **`GRow`+fill,
   `BlitRow`, and `FontAgain` separately inside one `TextAt`** gives the three numbers
   directly, and each of the three points at a different fix:

   - **`BlitRow` dominates** → build `BlitBox`; the per-row round trip is the bill.
   - **`FontAgain` dominates** → the remap is the bill and it is nearly free to fix: the
     font page only moves when `BlitRow`'s `TVCALL` moved it, and `tbox.asm` line 30
     already calls `MapB` *"a compare when nothing moved"* — so the compare is either not
     reached or not cheap.
   - **`GRow`+fill dominates** → the estimate above is wrong, and only then does hoisting
     `Glyph` out of the row loop (the strike's running pointer, ~4 ms) earn its change.

   **Order, from here:**
   1. ⭐ **`F.Opaq` is set and measured** (2026-09-21) — the table above.
   2. ⭐ **The icons are next**, because they are now 27 % of the repaint and they are the
      engine's own shape. Deciding it means deciding the palette question above (renumber
      to key on 0, or give the engine its own blobs in VRAM).
   3. Leave the text to `F.Opaq`. It is already the cheaper mechanism.
   4. ⭐ **Then the three-way `TextAt` measurement above**, before any of the Mac ideas is
      built. The only one it could vindicate is `BlitBox`; the glyph bank is already ruled
      out on arithmetic.
   5. ⛔ And none of this closes item 7: a repaint would have to reach ~150 ms. **The
      sticky button bit is the fix for item 7**, and it is independent of all of the
      above.
