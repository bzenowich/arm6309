# `software/desk/` — the desktop shell

`desk` is the Haiku-like desktop the boot ends at: a menu bar that pulls down, a column of application icons, and the **Tracker** file manager, whose window can be dragged — every step one `SS.Copy` on the card.

| | |
|---|---|
| 6809 source | `../nitros9` (branch `arm6309`), `level2/arm6309/cmds/desk.asm`, and the manager's listing in `modules/v3dir.inc` (shared with `v3trk`) |
| Icon art | `software/toolbox/tools/mktbox.py` — the ROM toolbox's page 64+ |
| Benches | `bench/run-v3desk.sh` (the shell, clicked at), `bench/run-v3files.sh` (the file manager, read off the pixels), `bench/run-v3move.sh` (the window move) — all driven by `PS2_SCRIPT`s in `bench/scripts/` |
| Demo video | `video/run-desk.sh` — boot to desktop, the file manager and the drag as a 1920 × 1080 H.264 file; `SHEET=1` for contact sheets |
| Docs | [`docs/boot-and-desktop.md`](docs/boot-and-desktop.md) |
| Reference | [`reference/`](reference/) |

⭐ **`run-v3desk.sh` is the one that drives a program with a MOUSE.** Everything else
here types a command and reads the picture; this one runs `desk` (the shell -
`software/desk/docs/boot-and-desktop.md` §3) off the card and clicks at it with a `PS2_SCRIPT`
(`software/emu/ps2script.h`), then reads every answer off the recorded frames:
the menu bar's rows, the pull-down appearing where nothing was, the highlight landing
on the item the pointer is over, the rectangle's CRC coming back to what was under it,
and **Paint's own page** as the evidence that a menu item forked a program. ⛔ With a
control that walks the bar and never clicks, in which the pull-down's rectangle must
hold exactly **one** picture for the whole run - a desktop that drew a menu on a timer
would pass every other claim. ⭐ Its geometry and its menu table are **parsed out of
`desk.asm`**, so an item renamed or un-greyed moves the claims with it. **47 claims.**

⭐ **`run-v3files.sh` is the one that READS THE SCREEN BACK AS TEXT.** `desk`'s file
manager (`software/desk/docs/boot-and-desktop.md` §3.6) lists a real directory, so the question is
not "did something get drawn" but "is what was drawn what is on the card". It
rebuilds every candidate name out of **the ROM's own font blob** — the two-bits-a-pixel
glyphs `software/toolbox/tools/mktbox.py` wrote into ROM pages 65 on — and matches
them against the pixels of each row; the names it prints are then compared with what
the host's **`os9 dir`** says is on the image. Two independent readers of one
directory, and the card's output in between. ⛔ With a control whose window is already
up (`desk /w3 N /SD0/DATA`) and whose mouse walks the list, both scroll arrows, the
menu bar and a desktop icon **without ever pressing** — the list must hold exactly one
picture, and **it must still be the real listing**, so a blank window is not what
passes it. ⭐ And a third run driving **`v3trk`** into the same rectangle from the
shell, because since 2026-09-21 the two programs share one directory reader
(`modules/v3dir.inc`). **65 claims.**
