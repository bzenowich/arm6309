#!/usr/bin/env python3
"""sessiondesk.py OUT - the DESKTOP session, as the emulator's inputs.

The brief: cold-start the machine, boot NitrOS-9 Level 2 off the SD card -
the ROM has carried no filesystem since 2026-09-22 - let the shell hand the
screen to
`desk`, and then drive the desktop with a mouse - open the file manager off
the `home` icon, walk into /DD/CMDS - NitrOS-9's own ~60 commands, which is
the only listing long enough to fill its twelve rows - and drag the window
round a figure-8 with video3's copy engine.  software/desk/docs/boot-and-desktop.md §3, milestones 1-4.

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

# ⭐ NO `reboot` HERE, AND THAT IS THE POINT.  machine.c used to enter at
# $8004 - boot.asm's handoff entry - so the POST and §10a's dialog never ran
# and the only way to SEE a boot was to reboot a running machine.  COLDBOOT=1
# starts the emulator at the RESET VECTOR instead, where the real machine
# starts, so this session simply boots.  run-desk.sh passes it.
LINES = [
    "iniz w3",
    # ⚠ /DD IS THE CARD.  One descriptor source assembled twice, so /DD and
    # /SD0 are the same disk - and /DD is what SysGo, init and armio.asm's
    # CoPath name, which is why it is the one used here.
    "chx /dd/cmds",
    "desk /w3 %d" % TICKS,
    "echo DONE-arm6309",
]

# ⭐ KEYED OFF desk's OWN CONSOLE LINES, not off a stopwatch.  Every trigger
# below is a string this session really transmits (desk.asm's Msg* table), so
# a caption cannot drift out of step with the thing it is describing - if the
# program stops saying it, the caption stops appearing rather than appearing
# over the wrong picture.
# ⚠ 78 CHARACTERS AND cp437, which is mkvideo.py's bitmap font: a longer line is
# TRUNCATED and a star or a warning sign comes out as `?`.  The sheet renders
# them properly and the video does not, so what goes here is plain ASCII.
CAPTIONS = [
    ("RKBoot", "A COLD START: the POST ran, found the SIMMs and the video card"),
    ("Krn tbs", "boot_sd read OS9Boot OFF THE CARD ('s'). The ROM carries no filesystem at all"),
    ("Shell+", "NitrOS-9 Level 2, loaded entirely from the SD card, on the serial console"),
    ("DESK-READY", "`desk`: a menu bar, desktop icons and an event loop on SS.Mouse"),
    ("DESK-ICON", "Drawn by the ROM TOOLBOX on page 64 - the one thing the ROM still carries"),
    ("DESK-DIR /DD", "The file manager, listing the REAL card - /DD and /SD0 are one disk"),
    ("DESK-SEL CMDS", "A click selects CMDS - there is no double-click timer to race"),
    ("DESK-DIR /DD/CMDS", "... and a second enters it: NitrOS-9's own commands, on the card"),
    ("DESK-GRAB", "THE TAB IS GRABBED: every step is ONE SS.Copy of 344 x 279 by the card"),
    ("DESK-DROP", "Dropped home bit-exact - the background it crossed came out of off-screen VRAM"),
    ("DESK-MENU Desk", "Desk > Quit, off the same menu bar the session started on"),
    ("DESK-BYE", "desk exits and the shell gets its prompt back"),
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
        [sys.executable, os.path.join(ROOT, "software", "desk", "bench", "mkdragps2.py")],
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
