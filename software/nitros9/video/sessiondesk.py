#!/usr/bin/env python3
"""sessiondesk.py OUT - the DESKTOP session, as the emulator's inputs.

The brief: boot NitrOS-9 Level 2 from ROM, let the shell hand the screen to
`desk`, and then drive the desktop with a mouse - open the file manager off
the `home` icon, walk into /DD/CMDS - NitrOS-9's own ~60 commands, which is
the only listing long enough to fill its twelve rows - and drag the window
round a figure-8 with video3's copy engine.  docs/boot-and-desktop.md §3, milestones 1-4.

⭐ NOTHING HERE IS A RECORDING.  session3.py's desktop is a stream of CoArm
escapes that `copy /sd0/data/v3desk /w3` plays back, and its drag is v3drag
walking a canned table of legs.  This session runs the PROGRAM: `desk` off
the SD card, an event loop on SS.Mouse, and a drag whose every step is the
window chasing where a PS/2 packet actually put the pointer.

It writes OUT/typed.txt (the shell) and OUT/drag.ps2 (the mouse), and holds
the CAPTIONS mkvideo.py keys off the serial stream.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# ⛔ THE ITERATION BOUND IS NOT A TIMEOUT.  desk's `ticks` argument is the
# bound CLAUDE.md asks every wait in this repository to carry; Quit is what
# normally ends the program.  ⛔ 9000 was NOT enough: F$Sleep 1 yields rather
# than sleeping a tick, so the loop runs at ~170 Hz and 9000 passes is 53 s -
# the drag was cut off by the bound, which desk reports as DESK-LIM now.
TICKS = 60000

# ⛔ `reboot` FIRST, AND IT IS THE ONLY WAY TO SEE THE BOOT DIALOG.
# software/demo/emu/machine.c enters at $8004 with boot.asm's handoff already
# applied (the map, the memory descriptor), so on a fresh start the POST and
# §10a's "looking for a disk" dialog NEVER RUN - the card stays dark until
# NitrOS-9 brings /W3 up, which is the 24 seconds of black this session used
# to open on.  `reboot` (F$Debug 255) re-enters at the reset vector with the
# map live and the ROM runs for real.  run-sdboot.sh says the same thing for
# the same reason.
# ⚠ SERIAL_GATE closes on every CR (machine.c:1105) and re-opens on the next
# prompt, so one SERIAL_IN survives the reboot: the lines below simply wait.
LINES = [
    "iniz w3",
    "chd /sd0",
    # ⚠ chx LAST: after it the only things the shell can fork are the card's
    # commands and shell+'s built-ins, which is the arrangement desk's own
    # launcher has to work in.
    "chx /sd0/cmds",
    "desk /w3 %d" % TICKS,
    "echo DONE-arm6309",
    # ⛔ LAST, AND THE VIDEO ENDS ON IT.  machine.c enters at $8004 with
    # boot.asm's handoff already applied, so on a fresh start the POST and
    # §10a's dialog NEVER RUN - the card is simply dark until NitrOS-9 brings
    # /W3 up.  `reboot` (F$Debug 255) re-enters at the reset vector and the
    # ROM runs for real.  ⚠ It does NOT survive: about a second later the
    # machine is in empty RAM and WILD stops the run, which is why this is the
    # last line rather than the first.  The dialog is on the card by then.
    # ⚠ chx BACK TO THE ROM DISK FIRST: `reboot` is one of the ROM's commands
    # and the execution directory is /SD0/CMDS by now, so without this the
    # shell answers "Error #216 - Path Name Not Found" and the ROM never runs.
    "chx /dd/cmds",
    "reboot",
]

# ⭐ KEYED OFF desk's OWN CONSOLE LINES, not off a stopwatch.  Every trigger
# below is a string this session really transmits (desk.asm's Msg* table), so
# a caption cannot drift out of step with the thing it is describing - if the
# program stops saying it, the caption stops appearing rather than appearing
# over the wrong picture.
CAPTIONS = [
    ("RKBoot", "NitrOS-9 Level 2 boots from ROM onto video3 - and an SD card in the socket"),

    ("02}/DD:", "A shell on the serial port. /DD is the ROM disk; /SD0 is the SD card"),
    ("desk /w3", "`desk` takes /W3: a menu bar, desktop icons, and an event loop on SS.Mouse"),
    ("DESK-READY", "Drawn by the ROM TOOLBOX on page 64 - there is no drawing code in desk at all"),
    ("DESK-ICON", "The pointer is video3's 16x16 HARDWARE SPRITE. One click selects `home`"),
    ("DESK-DIR /DD", "A second click OPENS it: the file manager, listing the REAL /DD - the ROM disk"),
    ("DESK-SEL CMDS", "A click selects CMDS - there is no double-click timer to race"),
    ("DESK-DIR /DD/CMDS", "... and a second enters it: NitrOS-9's own commands, twelve rows at 2.1 s"),
    ("DESK-GRAB", "⭐ THE TAB IS GRABBED: every step is ONE SS.Copy of 344 x 279 by the card"),
    ("DESK-DROP", "Dropped home bit-exact - the background it crossed came out of off-screen VRAM"),
    ("DESK-MENU Desk", "Desk > Quit, off the same menu bar the session started on"),
    ("DESK-BYE", "desk exits and the shell gets its prompt back"),
    # ⚠ ":reboot" AND NOT "DD:reboot": `chx` moves the EXECUTION directory and
    # the prompt still says /SD0, so the trigger has to be the command itself.
    # ⛔ And the dialog cannot have a trigger of its own - §10a runs before
    # there is a kernel, let alone a serial driver, so nothing is transmitted
    # while it is on screen.  This caption is keyed to the command that causes
    # it and stays up, which is why it is the last one in the list.
    (":reboot", "⭐ `reboot` re-enters at the RESET VECTOR: boot.asm's POST, and §10a's "
                "dialog - the Macintosh question, answered off the card"),
]


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: sessiondesk.py OUT")
    out = sys.argv[1]
    # ⚠ CR, not LF - this is a NitrOS-9 console.
    with open(os.path.join(out, "typed.txt"), "w") as f:
        f.write("".join(l + "\r" for l in LINES))
    # ⭐ THE MOUSE COMES FROM mkdragps2.py, which parses the travel box and
    # the window's corner out of desk.asm's own equates.  There is no second
    # copy of the geometry here, and that is deliberate.
    ps2 = subprocess.run(
        [sys.executable, os.path.join(ROOT, "video3", "bench", "mkdragps2.py")],
        env=dict(os.environ, SESSION="1"), capture_output=True, text=True)
    if ps2.returncode:
        sys.exit("FAIL  sessiondesk: mkdragps2.py: %s" % ps2.stderr.strip())
    with open(os.path.join(out, "drag.ps2"), "w") as f:
        f.write(ps2.stdout)
    moves = sum(1 for l in ps2.stdout.splitlines() if "move to" in l)
    print("ok    sessiondesk: %d lines, %d captions, %d mouse moves"
          % (len(LINES), len(CAPTIONS), moves))


if __name__ == "__main__":
    main()
