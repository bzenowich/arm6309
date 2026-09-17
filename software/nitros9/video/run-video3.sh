#!/bin/sh
# The VIDEO3 demo video: one scripted session on the host emulator, and the
# screen and the serial console side by side in an H.264 file.
#
# ⭐ V3=1 builds the port against video3 and VIDEO3=1 runs the emulator's
# video3 card model. video3/docs/demo-report.md is the write-up.
#
#   sh software/nitros9/video/run-video3.sh        (from the repository root)
#   NOBUILD=1   use the ROM already in build/
#   SHEET=1     contact sheets instead of the H.264 file: build3/sheet-*.png
#               (sheet3.py), in seconds rather than minutes - what a pass is
#               reviewed from before the full-motion file is worth making
#
# Writes software/nitros9/video/video3-demo.mp4. build/ keeps the ROM, the
# emulator's recordings and the console. ⚠ THE EMULATOR, NOT THE MACHINE: the
# video console has not run on machine_tb (docs/video-console.md).
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
V=software/nitros9/video
OUT=$ROOT/$V/build3
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { cat "$OUT/mkrom.log"; exit 1; }
fi
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c audio/refplayer/card.c
python3 $V/session3.py "$OUT"

STOP=$(printf '\nDONE-arm6309')
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 SERIAL_TIMES=serial.times \
   SERIAL_STOP="$STOP" PS2_KBD="$(cat kbd.txt)" PS2_KBD_GATE="PS/2 keyboard" \
   PS2_MOUSE="$(cat mouse.txt)" PS2_MOUSE_GATE="PS/2 mouse" WILD=1 \
   VIDEO3=1 ./emu arm6309_rom.bin . 600 > /dev/null 2> emu.log) || true
tail -1 "$OUT/emu.log"
grep -q "SERIAL_STOP seen" "$OUT/emu.log" || { grep -m1 -A3 "WILD\|FAIL" "$OUT/emu.log"; echo "FAIL  the session did not finish"; exit 1; }
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
if grep -n "Error #" "$OUT/console.txt"; then echo "FAIL  a command failed (build/console.txt)"; exit 1; fi

if [ -n "$SHEET" ]; then
  python3 $V/sheet3.py "$OUT" 3
  exit 0
fi
SESSION=session3 python3 $V/mkvideo.py "$OUT" "$ROOT/$V/video3-demo.mp4"
# ⛔ And CHECK IT, because a large recent file is not a finished one: ffmpeg
# writes the moov atom last. checkmp4.py says why this is a separate step.
python3 $V/checkmp4.py "$ROOT/$V/video3-demo.mp4" || exit 1
