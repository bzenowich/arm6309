#!/bin/sh
# ⭐ THE DESKTOP DEMO VIDEO: boot, the file manager, and a figure-8 drag.
# One scripted session on the host emulator, and the screen and the serial
# console side by side in an H.264 file.  docs/boot-and-desktop.md §3.
#
#   sh software/nitros9/video/run-desk.sh        (from the repository root)
#   NOBUILD=1   use the ROM and the card image already in build-desk/
#   NORUN=1     re-encode the recording that is already there
#   SHEET=1     contact sheets instead of the H.264 file: build-desk/sheet-*.png
#               (sheet3.py), in seconds rather than minutes - ⭐ WHAT A PASS IS
#               REVIEWED FROM before the full-motion file is worth making
#
# ⭐ IT RUNS THE PROGRAM, NOT A RECORDING.  session3.py's desktop is a byte
# stream played into a window and its drag is v3drag walking a canned table;
# this boots the machine, runs `desk` off the SD card and drives it with a
# PS2_SCRIPT, so every frame is the event loop answering a real packet.
#
# ⚠ THE EMULATOR, NOT THE MACHINE.  machine.c is the host model; the RTL
# benches are video3/bench/run-v3desk.sh and run-v3move.sh.
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
V=software/nitros9/video
OUT=$ROOT/$V/build-desk
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-150}
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
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
  # the card: the shell and the app its menu launches
  DATA="$OUT/data" sh software/nitros9/mksddisk.sh "$OUT/sd.img" desk v3paint \
    > "$OUT/mksddisk.log" 2>&1 || { cat "$OUT/mksddisk.log"
    echo "FAIL  the card did not build"; exit 1; }
  cat "$OUT/mksddisk.log"
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"
python3 $V/sessiondesk.py "$OUT"

if [ -z "$NORUN" ]; then
  STOP=$(printf '\nDONE-arm6309')
  # ⚠ SERIAL_TIMES is not optional: mkvideo.py's right-hand panel shows each
  # byte from the moment the emulator transmitted it, and the captions are
  # keyed off the same file.
  (cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_TIMES=serial.times SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     PS2_SCRIPT="$OUT/drag.ps2" PS2_SCRIPT_GATE="DESK-READY" \
     ./emu arm6309_rom.bin . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tail -1 "$OUT/emu.log"
  tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
  grep -q "SERIAL_STOP seen" "$OUT/emu.log" || {
    echo "FAIL  the session did not finish (see $OUT/console.txt)"; exit 1; }
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
