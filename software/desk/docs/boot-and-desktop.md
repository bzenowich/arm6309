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
really on the card, and since 2026-09-22 **its windows move**.

> **Status: §1 is BUILT (2026-09-20) — `software/boot/boot.asm` §10a, and
> `machine_tb`'s `disk` and `nodisk` scenarios read the picture off the
> connector. §3's MILESTONES 1 AND 2 ARE BUILT (2026-09-20) — `desk`, a
> NitrOS-9 command on the SD card, and `software/desk/bench/run-v3desk.sh` clicks at
> it with a `PS2_SCRIPT` and reads the answers off the frames. ⭐ **§3's
> MILESTONE 3 IS BUILT (2026-09-21)** — the file manager, and with it the
> desktop icons that §5 item 6 said were drawn and dead;
> `software/desk/bench/run-v3files.sh` reads the listing off the pixels and compares
> it with the host's `os9 dir`. ⭐ **§2 IS BUILT (2026-09-21)** — the machine
> reads the card before there is an OS (`boot.asm` §10b) and NitrOS-9's
> `boot_sd` loads `OS9Boot` off it — ⛔ **with no fallback since 2026-09-22**:
> the ROM carries no filesystem, so a machine with no bootable card blinks the
> question mark and never reaches a prompt.
> `software/nitros9/run-sdboot.sh` boots all three card states from reset.
> ⭐ **THE APPLICATIONS ARE ICONS (2026-09-22)** — Monster, BBS, ANSI Art,
> Stardew and Explore, §3.4.1; the BBS and the art became programs to do it, and
> the art itself had to be written rather than imported.
> ⭐ **§3's MILESTONE 4's WINDOW MOVE IS BUILT (2026-09-22)** — the manager's
> tab is grabbable and the card moves the window, one `SS.Copy` a step;
> `software/desk/bench/run-v3move.sh` reads the figure-8 off the frames and asserts
> the window went where the *mouse* went. **Closing, a second window, rename,
> copy and delete are still §3.5.**

---

## 0. The sequence, against what exists

| Mac 128K does | this machine | state |
|---|---|---|
| ROM finds the video hardware | `boot.asm`'s `vprobe` — writes `$A5`/`$5A` to `+$13` and reads back; video3 returns it, the archived card cannot (b2/b3 hardwired zero), an empty slot floats | ⭐ **built 2026-09-20** |
| clears the screen | the POST already paints all of 640 × 200 with the span writer | ⭐ built |
| a dialog, with an icon: *looking for a disk* | `boot.asm` §10a, drawn with the ROM toolbox | ⭐ **built 2026-09-20** — §1 |
| the icon changes when a disk is found | the same drawing path, and the Mac's blinking question mark when there is none | ⭐ **built 2026-09-20** — §1. ⭐ *found* means a card the ROM has read a boot signature off since 2026-09-21: §2 |
| loads the OS from the disk | `boot.asm` §10b reads block 0 before there is an OS; `boot_sd` reads `OS9Boot` off the card, and ⛔ **since 2026-09-22 there is no fallback** | ⭐ **built 2026-09-21** — §2, `sdcard.md` §9.5 |
| a desktop | `desk` — a menu bar, an event loop on the PS/2 mouse, icons on the Haiku desktop | ⭐ **built 2026-09-20** — §3 milestone 1. ⭐ The icons became clickable 2026-09-21 |
| a file manager | `desk`'s Tracker window, listing a real directory through `v3dir.inc` — the reader `v3trk` has always used | ⭐ **built 2026-09-21** — §3 milestone 3 |
| an application menu | `desk`'s **Applications** menu forks `v3paint`, `monster`, `stardew`, `v3bbs`, `v3art` and `tilescroll` off `/SD0/CMDS` | ⭐ **built 2026-09-20** — §3 milestone 2. ⭐ **All of them are desktop ICONS too since 2026-09-22** — §3.4.1 |
| a window you drag by its title bar | `desk`'s tab grab, and **the copy engine moves the pixels** — the CPU never touches one | ⭐ **built 2026-09-22** — §3.7 |

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
| *no toolbox* | ⚠ page 64 is 8 KB of zeros in a build without `-DV3=1`, and in a bare `make -C software/boot rom`. The dialog is **skipped**, not half drawn | `$63` |

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
— A09 cannot include lwasm source. [`checkcg.py`](../../nitros9/tools/checkcg.py)
re-derives all 22 with lwasm off the real `armvid.d` and `software/nitros9/mkrom.sh`
refuses to build a ROM whose two halves disagree.

**Cost: two ROM pages mapped for the length of the dialog, ~790 bytes of ROM, eight
bytes of variables and a stack in block 0 — plus `CoG`'s scratch and `tbox`'s own
`TB`, which are SIMM the POST was not using.**

## 2. Booting NitrOS-9 off the card

⭐ **Built 2026-09-21.** `OS9Boot` comes off the SD card, and ⛔ **since 2026-09-22 there
is nowhere else it can come from**: the ROM carries no filesystem, so no bootable card is
a machine that stops at §10a's question mark. `hardware/storage/docs/sdcard.md` §9.5 is the design;
this is what it is made of and what it changed here.

**Two readers, because there are two moments.** The boot ROM has to read the card before
there is an OS; the kernel's `F$Boot` module has to read it again once there is.

| | |
|---|---|
| `boot.asm` **§10b** | the ROM's reader: §9.0's initialisation and §9.1's `CMD17` of block 0, ~640 bytes. No filesystem, no directory walk, no write path, **no block buffer** — the eight bytes the verdict needs are picked out of the 512 as they go by. ⚠ It never loads anything. Its whole output is which of §1's three pictures is true |
| `boot_sd.asm` | the NitrOS-9 `F$Boot` module (nitros9 `level2/arm6309/modules/`), 881 bytes of the loader's 896: `HWInit`/`HWTerm`/`HWRead` for `boot_common.asm`. It reads `OS9Boot` off the card, and ⛔ when it cannot it returns `E$NotRdy` — `BSNone`, since 2026-09-22 — so the loader fails and §10a's question mark is what the machine shows |

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

⛔ **AND SINCE 2026-09-22 THERE IS NOTHING TO FALL BACK TO.** The ROM used to carry
the whole NitrOS-9 distribution — 61 pages, **47.7 % of the flash** — mounted as a
bootable RBF disk, so a bad card meant a rescue prompt rather than a stop. Pages 3–63
are zeros now: the ROM finds the card, draws the dialog and boots from it, and a
machine with no bootable card blinks the question mark for ever. `machine.md` §7.2 has
the page map and `hardware/storage/docs/sdcard.md` question 15 the decision.

⭐ **That is not a regression, it is the point.** A fallback that works is a fallback
that *hides a card that does not*: `run-sdboot.sh`'s own warning — "a shell appeared is
not evidence" — existed only because the ROM disk reached the same prompt. With the
ROM disk gone, reaching a shell **is** the evidence.

⭐ **`/DD` AND `/SD0` ARE THE SAME CARD.** One descriptor source (`sddesc.asm`)
assembled twice, so `OS9Boot`, the whole command set, `SYS`, `MODULES` and `startup`
answer to either name — and `/DD` is what `SysGo`, `init` and `armio.asm`'s `CoPath`
already named. ⚠ `SysGo` points the execution directory at the card **in `sysgo.asm`,
not in `startup`**: SysGo *forks* a shell to run `startup`, so a `chx` there changes
the child's execution directory and nothing else.

⭐ **And `boot_sd` still says what it did**: one character through `D.BtBug`, between
`krn`'s `tb` and `boot_common`'s `0` — **`s`** for a card it read, **`n`** for no
bootable card, which is now a boot that fails rather than one that falls back.
`software/nitros9/run-sdboot.sh` (**45 claims**) is the bench, and it asserts the same
thing a second, independent way — the card carries a **different** `OS9Boot`, with two
extra modules in it, so `mdir` names them only on a machine that read the card.

---

## 3. The desktop, which is the whole job

⭐ **The event loop, the menu bar and the launcher are built** (2026-09-20):
[`desk.asm`](../../nitros9/level2/arm6309/cmds/desk.asm), a NitrOS-9 command on the SD
card beside the demos it launches. It is an application, not ROM — §4 — and its own
header is the detailed design. `software/desk/bench/run-v3desk.sh` is the bench.

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
| `v3drag` | ⭐ **the window move, proven before it was adopted.** `desk` does not call it and does not share its code — it shares its *shape* (§3.7): draw at the new place first, then put back only the sliver vacated. ⛔ What `desk` could **not** take is its backing store, and the reason is arithmetic — see §3.7 |

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

Two titles — **Desk** (About, Quit) and **Applications** (Paint, Monsterland, Stardew,
BBS, ANSI Art and Explore) — in an 18-pixel bar of `C.ITab` with one row of `C.Frame` under it.
A pull-down is a `tbox` bevel; an item is highlighted by repainting its rectangle in
`C.Sel` and its label in the `sel` ramp, and unhighlighted by repainting it in `C.Panel`.

⭐ **A greyed item is refused the highlight as well as the action**, so hovering it says so
too — the mechanism is `A.Dis` and it is what carried `Stardew` while it was specified and
not built. ⭐ **All four items are live since 2026-09-21**, when
[`software/stardew/docs/stardew.md`](../../stardew/docs/stardew.md)'s farm was built; `history.md` has
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

### 3.4 `v3paint`, `v3bbs`, `v3art` — why an icon cannot fork a stream

`v3paint` was a *data file*; the menu needs a *program*. So
[`v3strm.inc`](../../nitros9/level2/arm6309/cmds/v3strm.inc) is the smallest honest one:
it opens `/SD0/DATA/<name>`, sends it to its own standard output, and holds the picture up.
The stream's own first escapes are `DWSet`, `Select` and `Pal`, so the program knows
nothing about the card, the toolbox or the palette.

⭐ **THREE OF THEM SINCE 2026-09-22, OUT OF ONE BODY.** `v3bbs` and `v3art` had the same
problem and the same answer, and the three differ in a module name, a file name and a
console token — so the body is an lwasm **macro** and each program is those three
strings. ⚠ Three copies of 170 lines is three places for a fix to be applied twice and
forgotten once, which this repository has already paid for once this week.

⛔ **`v3art` is Blocktronics' *we-tortuga*, and nothing else** (since 2026-09-24). The file
is **not in this repository** — it goes in `software/paint/reference/` — so on a clone
without it `v3show.py` leaves `v3art` out and the ANSI-Art icon forks nothing. That is
the owner's choice; the project's own piece that filled the gap for two days is in
`software/archive/paint/ansi-original.py`.

### 3.4.1 ⭐ The applications are ICONS — built 2026-09-22

`IcTab` carries **Monster, BBS, ANSI Art, Stardew and Explore** in a column at
x 568, between the file manager's home position (which ends at 380) and the screen's
edge; `NICON` is 11, and the Applications menu carries the same names. Their
art — `monster`, `farm`, `world` — was **appended** to `mktbox.py`'s
`ICON_NAMES`, because this table names art by number and an insertion repaints every
icon after it with its neighbour's picture, silently. ⚠ Art number 16 is `pinball`'s,
whose program was retired; it stays in `ICON_NAMES` so that nothing after it is renumbered.

⚠ **The column's pitch is 72 and not 80** since 2026-09-23, which is what made six of
them fit; there are five. An icon's cell is `GEO.ICONY+14` = 48 tall (the 32 × 32 art and its label),
so a sixth at 80 would start at 434 and end at **482** — two rows past `GEO.SCRH`. At
72 the column runs 34..369.

⭐ **Explore is `tilescroll`** (`software/tilescroll/docs/scrolling.md`): a camera roaming a 4096 × 2048
world with the hero in the middle of it. ⚠ It is the
only scene here that runs in **`VMODE` 11**, so its own `DWSet` asks for a 640 × 480
screen; the desktop's is untouched, because `A.Run` gives its window up first.

⚠ **AND A SECOND CLICK NEEDS ROOM.** Selecting an icon repaints the icon column and
`desk` samples the button once a loop pass, so a launch click 0.9 s after the selecting
one is not late — it is **gone**, and the console shows `DESK-ICON` with no `DESK-RUN`
after it. 3 s apart works. It is the same rule this document already records for a
click that lands inside `DrawAll`.

⚠ **At full right travel the manager crosses them**, which is wanted rather than
avoided: it is exactly the question §3.7's backing store answers, and
`checkmove.py` reads `IcTab` out of the source to find which ones the drag went over.

⛔ **AND IT COST RESPONSIVENESS, MEASURED.** `desk` repaints the *whole* desktop on a
menu dismissal and on a child's return (`DrawAll`), and samples the mouse button **once
a loop pass** — so a click that lands inside a repaint is not late, it is **gone**. Five
more icons took the launch round-trip from ~26 s to **46 s**: `checkdesk.py` records the
click at 45.8 s, Paint's page on the card from 70.4 s to 91.2 s, and the desktop back at
92.1 s. Thirteen of `run-v3desk.sh`'s claims failed describing a desktop that was merely
still drawing, and `desk`'s own 5,000-pass bound cut the script short.
⚠ **`DrawAll` is O(icons) and there are about to be twelve.** The honest fix is the one
§3.7 already built for the window — keep the background and restore a rectangle — and it
is not done.

### 3.5 What is left

3. **The file manager (built 2026-09-21; §3.6).**
4. **Windows that move (built 2026-09-22; §3.7) and close.** The move is done; **closing
   is not**, and neither is the second window it was blocking. Two windows with no
   clipping is whichever was drawn last (`v3show.py`'s `stream_cmds` says so), which is
   why the move had to come first. Rename, copy and delete after.
   ⭐ **And §3.7's store is what unblocks the second window**, which is why the move came
   first: `SB` holds whatever background is behind the manager, so another window under it
   is restored like anything else. ⚠ What is *not* solved is the second window being
   dragged — one region is kept, and it is the manager's.

### 3.6 The file manager — built

⭐ **A Tracker window on the desktop, listing a real directory**, opened from the **Go**
menu (`Files`, `Up`, `Open`, `Close`) or by clicking the desktop's disk icon.
`software/desk/bench/run-v3files.sh` is the bench.

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
`marks.txt` in picoseconds (`software/archive/demo/demo.asm`'s `MARK`, `monster`'s instrument):
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

### 3.7 The window moves, and the card moves it — built

⭐ **A press in the tab grabs the window; every pass after it is one `SS.Copy` of the
window's bounding box from where it was to where the pointer has put it, and a restore of
the sliver it vacated out of an off-screen copy of the background.** The list is never
redrawn — which is the whole point, because `DrawFiles` is 2,957 ms and a pass has 16.7.
`software/desk/bench/run-v3move.sh` is the bench.

The window's place is **model**, exactly as its listing is: two words, `fdx` and `fdy`,
offsets from `FM.X`/`FM.Y`. `SetX`/`SetY` add them on the way out and `FileHit` takes them
off on the way in, so all forty drawing sites and every hit test stay written in the
literal `FM.*` they always were, and a launch (§3.3's `DWEnd`) takes the pixels and not
the position.

#### The backing store, and the number that sized the window

⛔ **`FM.W` IS 344, AND TWO DIFFERENT LIMITS SET IT.** `SB` holds the background of a
region around the window — the window plus `Marg` on every side — and the only off-screen
VRAM wide enough is the scroll margin at columns 640–1023 (§4 of `hardware/video3/docs/plan.md`).

| limit | what it says |
|---|---|
| width | `FM.W + 2·Marg ≤ 384`, the margin's columns |
| ⛔ **height** | `FM.H + FM.TABH + 2·Marg ≤ 320`, because **`tbox.asm`'s glyph strike is in the same margin** — `SK.Col` 640, `SK.Row` 320, three slots of 51 rows |

**The height is the binding one**: it caps `Marg` at **20**, which then leaves the width at
**344**. ⚠ **It was 420 until 2026-09-22**, with no store at all; `history.md` has what
that cost.

⛔ **A store that ran past `SK.Row` ATE THE TEXT.** With `Marg` = 50 the region was 379
rows and overlapped the strike by 59 — and every name in the listing came out as a **solid
bar**. That reads as a font bug and is a memory conflict; nothing in the drag looked wrong
at all. `software/desk/bench/checkmove.py` asserts the clearance against `tbox.asm`'s own
`SK.Row` rather than trusting a comment.

⚠ **`Marg` is also the step cap and the re-base interval**, so sharing the margin with the
toolbox costs drag speed as well as width. ⭐ **The height never had to move**, so the list
still shows all **12** of its rows.

⭐ **And there is no `SW`.** `v3drag` keeps its window's own pixels off-screen as well,
because it *redraws* the window from there every step. This moves screen to screen, old
position to new, so the pixels never leave the card. ⚠ That matters arithmetically, not
just aesthetically: `SW` + `SB` stacked would be 279 + 379 = **658 rows** and the margin
has 480. **A design with both does not fit at any width.**

| | |
|---|---|
| the move | **one** copy of the whole 344 × 279 bounding box, screen to screen, ~20 ms — or ~40 when it moves down or right and `vidcpy3.asm` stages it |
| the restore | `DVac` puts back old-box-minus-new-box **out of `SB`**. That is at most **two** rectangles, each taking the old box's full extent on the other axis; they overlap at the corner and are written twice with the same background, which buys no case analysis beyond the sign of each delta |
| the re-base | `NewB`, when the *next* box would not be inside the region. ⛔ **The hole first, and it is a store-to-store copy**: the background under the window cannot come off the screen, because the window is on it. Then four screen-to-store pieces which are exactly region-minus-window, so no pixel is copied twice and none is missed |
| the step cap | **`Marg`.** `NewB` re-bases around where the window *is*, so the next box has to be within `Marg` of it. ⚠ A hand faster than 50 px a pass drags at 50 a pass and the pointer runs ahead of the tab — visible, and far better than v3drag's lines 726–732, which record what a margin smaller than the step does: black lines beside the tab, first flickering and then stuck |

⛔ **`InFit` MUST FIRE BEFORE THE MOVE, NOT AFTER.** `NewB` reads the hole out of the
**old** store, which only holds it while the window is still inside the old region. A test
that waits until the window has actually left re-bases one step too late and the store
fills with whatever was on the screen outside it. That is `v3drag`'s lines 655–660 and it
cost that program a day.

⛔ **AND THE STORE IS TAKEN WHERE THE BACKGROUND IS REALLY ON THE SCREEN** — `DrawAll`,
between `DrawIcons` and `DrawFiles`, and `FMShow` **only when no window was up**.

⛔ **AND THE GUARD ITSELF HAD THE REAL BUG IN IT: `PULS` DOES NOT AFFECT CC.**
`puls a` / `bne` tests the flags the *previous* instruction left — here `ReadDir`'s last
compare — and not the byte just pulled. So the guard fired on the directory reader's
condition codes, `PhotoB` ran on a navigation redraw with the window up, and **the store
swallowed the window**. It needs an explicit `tsta`. ⚠ This is `grep '^FAIL'` and
`sh -c "! helper"` in a third costume: *an instruction that looks like it sets the flags
and does not*, producing a confident wrong answer rather than an error.

⚠ **`FMShow` IS THE NAVIGATION PATH TOO**, and that is what made the guard necessary.
`ActUp`, `ActGoIn` and `OpenEnt` all reach it, and taking the store there puts **the
window itself** in it — after which `DVac` faithfully restores window pixels into the
trail and the drag leaves a second window smeared across the desktop. The guard is the
previous value of `fopen`, read before `FMShow` sets it.

⛔ **And the bench could not see what was wrong.** Its window detector simply reported the
window as *undetectable* from the moment of the grab; the picture — two windows, one of
them a trail — only appeared when a frame was rendered as ASCII and looked at. That is
`CLAUDE.md`'s rule paying out again: **trace when the symptom is control flow; look at the
data when the symptom is a wrong answer of the right shape.**

#### The notch, and the tab's width

⛔ **`tbox.asm`'s `TWin` makes the tab only `TextW(title, bold) + 52` wide**, so the window
is an **L** and the rectangle around it has a notch at the top right — background, not
window. One copy of the bounding box carries that background to the new place, and ⛔
**`DVac` cannot put it back**, because the notch at the *new* position is inside the new
box and `DVac` only restores old-minus-new.

⛔ **AND NOTHING HANDS THE TAB'S WIDTH BACK.** The toolbox escape interface is one-way and
call 10's `TB.TW` lives in the toolbox's own RAM, so `desk` cannot ask how wide the tab it
just requested came out. ⭐ **So it lays the title out itself**: `desk.asm` carries the
bold face's 95 advance widths, generated by `mktbox.py --widths` from the same font the ROM
is built with, and `TabWide` is `TextW`'s own sum plus 52. ⚠ The fallback is `Glyph`'s —
a code outside 32–126 is *drawn* as `?` and so is *measured* as `?` — and it stops at 55
characters because `DrawFiles` does. ⭐ Generated and pasted, exactly as `v3drag` carries
`mklegs.py`'s table, and `checkmove.py` recomputes it from the font and fails if the two
have drifted.

⚠ **It was painted over for one build.** The first version filled the whole tab band with
`C.ITab` so the bounding box would be all window and one copy would be exact — which
worked, and replaced the desktop beside the tab with a grey slab. `history.md` has it.

With the width known, the move is `v3drag`'s shape: **two copies** (the tab, then the
body) and **three** restores in `DVac` — the two strips plus the notch at the new position:

```
x = newx + TabW        w = FM.W - TabW - max(0, dx)
y = pwy + max(0, dy)   h = FM.TABH + min(0, dy)
```

⛔ **That closed form is the one `v3drag` got wrong first time** (its lines 357–362):
restoring the tab's right edge over `FM.TABH` rows and the notch over `dy` rows from `TabW`
leaves `|dx| × dy` pixels uncovered on a down-left step — a staircase of white bevel pixels
climbing away from the title. ⚠ `h` goes to zero or below when a step is taller than the
tab (the cap is `Marg` = 20, the tab is 19), so `VCopy` skips an empty rectangle.

⛔ **AND THE ORDER OF THE TWO COPIES DEPENDS ON THE DIRECTION**, because this is a
**screen-to-screen** move and one rectangle's destination is the other's source. Moving
**down**, the new tab band lands on rows that are still the *old body*: copy the tab first
and it destroys body pixels the body copy has not read yet. Moving **up** it is the other
way about. So `dy > 0` copies the body first and `dy ≤ 0` the tab first. ⚠ **`v3drag`
never meets this** — it redraws from an off-screen `SW`, so its source is never the screen
it is writing on. The symptom here was that the desktop restored perfectly and the
**window's own frame** came back with a band of stale pixels `FM.TABH` tall.

⭐ **`TabHit` uses the same width**, so the grab band is the tab that was drawn. It used to
be the window's full `FM.W` and there was grab surface on bare desktop beside the tab.

#### What it costs, and what the bench establishes

⭐ **The travel box is the whole screen** — x 0–296, tab-y 19–201, the physical limits and
nothing else. The window is dragged **straight over the desktop icons** and they come back,
which is the entire difference between a store and a flat fill.

⭐ **A step is 20–40 ms** plus the loop's `F$Sleep 1`. ⚠ **Sampling the mouse faster does
not make the drag smoother**: `desk` chases the pointer's *absolute* position, so the
window falls behind and the pointer visibly detaches from the tab it is holding.

⭐ **What the bench establishes**, off the pixels: the window took dozens of distinct
positions, every one inside the travel box, **every one a position the PS/2 script put the
pointer at** less the grab offset — ⛔ which is the claim that separates this from
`v3drag`, because a canned curve satisfies every other claim here — that it came home
**bit-exact**, and ⛔ **that every pixel outside the window is the one it was before the
grab**, icons included. ⛔ With a control that walks the same path and never presses, in
which the window holds exactly **one** position.

⚠ **`DESK-LIM` is not `DESK-BYE`.** Both exits printed `DESK-BYE` until 2026-09-22, so
"the desktop stopped" and "the desktop was told to stop" were the same line on the console
— and a drag that ended early read exactly like a `Quit` that had been clicked. The
iteration bound says so in its own words now.

⚠ **And the bit-exact claim has a trap in it**, paid for on 2026-09-22: **the pointer is
in the picture.** video3 composites it as a 16 × 16 sprite and the script parks it on the
tab to grab, where its bottom six rows reach into the frame. Comparing the last home frame
of the run against the last one before the grab compares a picture with the pointer in it
against one without — it failed on a perfectly good drag, and the CRC differed by exactly
those six rows.

---

## 4. What this costs the ROM, and the division of labour

The owner's framing has been consistent: **the ROM is for toolbox routines, the card is for
apps.** Since 2026-09-22 that is literally true — there is no ROM disk, pages 3–63 are
zeros, and the operating system, the demos and their data are all on the card.

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
3. **Whether the ROM disk stays bootable (answered 2026-09-21, and REVERSED 2026-09-22;
   §2).** It does not stay at all — it is gone, ROM pages 3–63 are zeros, and there is no
   configuration in which a machine with no bootable card reaches a prompt. ⭐ And `/DD`
   did follow `OS9Boot` onto the card: `sddesc.asm` is assembled twice, so the one disk
   is both `/DD` and `/SD0`. `hardware/storage/docs/sdcard.md` question 15.
4. **The mouse under an exclusive-screen program (answered 2026-09-20; §3.3).** The
   desktop gives its window up with `DWEnd` before it forks and sleeps in `F$Wait` while
   the child has the card. ⚠ **What is still open is the part nobody wants**: for the ~45 s
   a child owns the screen the desktop is deaf, and there is no way to leave it — no
   command key, no force-quit, and no second screen to switch back to. A shell that cannot
   interrupt what it launched is a shell with one application.
   ⛔ **And the floor is not the child's run time — it is ~26 s, measured 2026-09-21.**
   `software/desk/bench/run-v3desk.sh` clicks Stardew on a card that carries the module and not
   its world, so the scene gets as far as reporting the missing file and exits; the
   recording still shows the card on the child's 640 × 400 screen from **96.2 s to
   114.4 s**, and the desktop takes no click before then. The child's `DWSet`, the
   desktop's `DWSet` back and its whole `DrawAll` all go through CoArm's toolbox escapes,
   which is where the time is. ⚠ The bench's mouse script waits that out with an absolute
   `at`, and a relative delay there is a Quit that is never seen.
5. **The desktop's four applications all launch (answered 2026-09-21; §3.2).** `stardew`
   was the last greyed item; its scene is built
   ([`software/stardew/docs/stardew.md`](../../stardew/docs/stardew.md), and
   `software/stardew/bench/run-v3star.sh`) and the item is `A.Run` like the other three. ⚠ What is
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
   [`hardware/video3/docs/keyed-copy.md`](../../../hardware/video3/docs/keyed-copy.md) describes a copy that skips
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

   ⭐ **A 16 × 16 icon at one copy each is 12 × 87 µs = ~1 ms a repaint against 565 ms**
   (`monster`'s ~87 µs of set-up, which a copy costs whatever its size). That is the case
   for doing the icons, and it stands.

   ⭐⭐ **AND IT IS ALSO THE CASE FOR DOING THE TYPE — BUILT AND MEASURED 2026-09-22.**
   The strike is in `tbox.asm` (`SkHave`/`SkBuild`/`SkText`) and **toolbox call 0 picks it
   whenever it is safe to**, so `desk`'s own text takes it: a forty-character line costs
   **33.42 ms against `F.Opaq`'s 222.89 — 6.7×**, drawing pixel-identical output
   (`run-v3text.sh`, 29 claims). ⛔ **A glyph costs 769 µs, not the 87 this paragraph
   assumed** — the per-copy call through the toolbox is nine times `monster`'s figure, and
   `proportional-font.md` §6.1 is where that is taken apart. The estimate below is kept
   because its *direction* was right and the size of its error is the finding.
   A per-glyph blit at the same 87 µs is
   **~3.5 ms for a forty-character title, against the 218.64 ms `F.Opaq` costs** for one
   (`demo-report.md` §16) and the 71.4 ms measured above for seven characters. **The
   engine wins on big rectangles and loses on small ones** is true of a copy against
   *another copy*; against this machine's software text a 12 px glyph is not the wrong
   shape by anything like enough to matter. ⚠ What a glyph cache loses to is a **string**
   cache — one copy of a pre-composed line, `keyed-copy.md` §3.2 — and the two are not
   alternatives: a strike pays on the first draw and a string cache only on the second.

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

   ⚠ **A GLYPH CACHE IN MAIN MEMORY IS DEAD, AND `TB.NTab` IS WHY.** The obvious
   borrow — "pre-expand each glyph to destination bytes for its ramp, so drawing is a
   `memcpy`" — assumes the expansion is the cost. It is not: a nibble is one table index
   and one `std`, which is **two pixels an instruction**, and a `memcpy` of pre-expanded
   bytes is also two pixels an instruction. The bank would cost ~275 KB across three
   ramps **to run the same speed**. The 32-byte table in RAM already bought the win; it
   is dated in `tbox.asm` at *"~45 cycles a pixel"* saved.

   ⛔ **THAT ARGUMENT DOES NOT REACH A CACHE IN VRAM, AND AN EARLIER DRAFT SAID IT DID.**
   It compares CPU-expanding against CPU-copying and finds them equal — which they are.
   A strike in VRAM is copied by **neither**: the engine moves it at 0.247 µs a byte, and
   the CPU's part is six register stores. More to the point, a strike deletes `TB.Buf`
   entirely, and with it **the seventeen `BlitRow`s and seventeen `FontAgain`s that the
   next paragraph identifies as ~60 ms of the 71**. The residual this section finds is
   exactly what the rejected design removes.
   [`proportional-font.md`](../../toolbox/docs/proportional-font.md) is that argument in full.

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
   3. ⭐ **Flatten the window tab** — gradient for two or three rows at each edge, a flat
      band behind the text. `RPaper`'s `255` becomes a palette index, `F.Opaq` starts
      working on the most-drawn text in the GUI, and the only case that wanted a colour
      key for text goes away — and with it the palette renumber above.
      [`proportional-font.md`](../../toolbox/docs/proportional-font.md) §4.4.
   4. ⭐⭐ ~~Then the three-way `TextAt` measurement, and one glyph blitted out of a
      strike~~ — **DONE 2026-09-22, and the strike is what shipped.** `Text` (call 0)
      takes it when the call is opaque and every glyph is inside the clip, and composes
      otherwise, so nothing had to change in `desk`. **6.7× on a forty-character line**,
      gated by `run-v3text.sh` (29), `run-v3desk.sh` (48) and `run-v3files.sh` (65).
      ⛔ **Two things the build taught that the estimate could not**: the cache must hold
      **one strike per (font, ramp)** — a list whose selected row is a different ramp from
      the other eleven would otherwise rebuild three times a repaint, at ~556 ms a build,
      which is *slower than no strike at all* — and it must be **invalidated when the
      screen changes**, because a forked program takes the margin the strike lives in
      (`armvid.d` `CG.SGen`). `BlitBox` is moot: a strike deletes the row loop it would
      have moved.
   5. ⛔ And none of this closes item 7: a repaint would have to reach ~150 ms. **The
      sticky button bit is the fix for item 7**, and it is independent of all of the
      above.
