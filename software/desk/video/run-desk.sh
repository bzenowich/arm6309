#!/bin/sh
# ⭐ THE DESKTOP DEMO VIDEO: boot, the file manager, and a figure-8 drag.
# One scripted session on the host emulator, and the screen and the serial
# console side by side in an H.264 file.  software/desk/docs/boot-and-desktop.md §3.
#
#   sh software/desk/video/run-desk.sh        (from the repository root)
#   NOBUILD=1   use the ROM and the card image already in build/video/
#   NORUN=1     re-encode the recording that is already there
#   SHEET=1     contact sheets instead of the H.264 file: build/video/sheet-*.png
#               (sheet3.py), in seconds rather than minutes - ⭐ WHAT A PASS IS
#               REVIEWED FROM before the full-motion file is worth making
#
# ⭐ IT RUNS THE PROGRAM, NOT A RECORDING.  session3.py's desktop is a byte
# stream played into a window and its drag is v3drag walking a canned table;
# this boots the machine, runs `desk` off the SD card and drives it with a
# PS2_SCRIPT, so every frame is the event loop answering a real packet.
#
# ⚠ THE EMULATOR, NOT THE MACHINE.  machine.c is the host model; the RTL
# benches are software/desk/bench/run-v3desk.sh and run-v3move.sh.
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
V=software/desk/video
OUT=${OUT:-$ROOT/software/desk/build/video}
# ⚠ 200: a COLD start pays for boot.asm's whole POST before NitrOS-9 begins.
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-200}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
[ -f "$NITROS9DIR/level2/arm6309/cmds/desk.asm" ] || {
  echo "FAIL  no ../nitros9 on its arm6309 branch"; exit 1; }

if [ -z "$NOBUILD" ]; then
  # ⛔ V3=1 OR NOTHING.  desk, the toolbox and SS.Copy are all inside
  # `IFNE V3` (defs/armvid.d, defs/arm6309.d, recipes/arm6309/arm6309.mak
  # §DEMOS), so a build without it has no desktop to run at all.
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
  # ⛔ THE CARD IS THE SYSTEM, since 2026-09-22.  The ROM carries the toolbox
  # and no filesystem at all, so an ordinary data card here is not a poor
  # demonstration - it is a machine that never starts.  mksyscard.sh is what
  # blesses it: NitrOS-9's bootfile at LSN 0 +$F0, its commands in /CMDS and
  # its modules in /MODULES, all out of the port's own recipe.
  OUT="$OUT" DATA="$OUT/data" NAME="arm6309 boot" \
  # ⭐ EVERY APPLICATION THE DESKTOP CAN LAUNCH, because since 2026-09-22 each
  # is a clickable ICON (desk.asm's IcTab) and an icon whose module is not on
  # the card is one that draws and answers E$MNF.
    sh software/nitros9/mksyscard.sh "$OUT/sd.img" desk v3paint pinball monster stardew v3bbs v3art \
    > "$OUT/mksddisk.log" 2>&1 || { cat "$OUT/mksddisk.log"
    echo "FAIL  the card did not build"; exit 1; }
  cat "$OUT/mksddisk.log"
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"
python3 $V/sessiondesk.py "$OUT"

if [ -z "$NORUN" ]; then
  STOP=$(printf '\nDONE-arm6309')
  # ⚠ SERIAL_TIMES is not optional: mkvideo.py's right-hand panel shows each
  # byte from the moment the emulator transmitted it, and the captions are
  # keyed off the same file.
  # ⭐ COLDBOOT=1: the emulator enters at the RESET VECTOR, so boot.asm's POST
  # and §10a's dialog are the opening of the video rather than something a
  # `reboot` has to be smuggled in to show (sessiondesk.py says why).
  # ⛔ SERIAL_STOP, WHICH THIS SCRIPT COMPUTED AND NEVER PASSED: without it the
  # session ran the full SECONDS_OF_MACHINE and the last 100 s of the recording
  # were a still desktop after `desk` had already quit.  The run ends at the
  # `echo` now, so the video is as long as the demonstration.
  (cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" \
     SERIAL_TIMES=serial.times WILD=1 VIDEO3=1 COLDBOOT=1 SDIMG="$OUT/sd.img" \
     PS2_SCRIPT="$OUT/drag.ps2" PS2_SCRIPT_GATE="DESK-READY" \
     ./emu arm6309_rom.bin . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tail -1 "$OUT/emu.log"
  tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
  grep -q "DONE-arm6309" "$OUT/console.txt" || {
    echo "FAIL  the session did not finish (see $OUT/console.txt)"; exit 1; }
  # ⛔ AND THE BOOT ROM HAS TO HAVE RUN, with the card found.  $60 is the
  # dialog up, $64 the ROM's own read of block 0, $61 "Disk found".
  for pr in 60 64 61; do
    grep -q "progress \$$pr" "$OUT/emu.log" || {
      echo "FAIL  the cold boot never reached boot.asm's \$$pr"; exit 1; }
  done
  if grep -n "Error #" "$OUT/console.txt"; then
    echo "FAIL  a command failed ($OUT/console.txt)"; exit 1; fi
  # ⛔ AND THE DRAG HAS TO HAVE HAPPENED.  A session that boots, lists the
  # directory and never grabs the tab reaches the shell prompt looking
  # exactly like a good one; these two lines are the difference.
  for m in DESK-DIR DESK-GRAB DESK-DROP; do
    grep -q "$m" "$OUT/console.txt" || { echo "FAIL  no $m on the console"; exit 1; }
  done
fi

if [ -n "$SHEET" ]; then
  SESSION=sessiondesk python3 $V/sheet3.py "$OUT" 3
  exit 0
fi
SESSION=sessiondesk python3 $V/mkvideo.py "$OUT" "$ROOT/$V/desk-demo.mp4"
# ⛔ AND CHECK IT: a large recent file is not a finished one, because ffmpeg
# writes the moov atom last.  checkmp4.py's docstring says why it is separate.
python3 $V/checkmp4.py "$ROOT/$V/desk-demo.mp4" || exit 1
