#!/bin/sh
# The NitrOS-9 progress video: one scripted session on the host emulator, and
# the screen and the serial console side by side in an H.264 file.
#
#   sh software/nitros9/video/run-video.sh        (from the repository root)
#   NOBUILD=1   use the ROM already in build/
#
# Writes software/nitros9/video/nitros9-progress.mp4. build/ keeps the ROM, the
# emulator's recordings and the console. ⚠ THE EMULATOR, NOT THE MACHINE: the
# video console has not run on machine_tb (docs/video-console.md).
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
V=software/nitros9/video
OUT=$ROOT/$V/build
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  # ⚠ CMDS_EXTRA: the demos live on an SD card now (software/nitros9/mksddisk.sh);
  # session.py types these three at /DD with an empty socket, so they are asked
  # for by name.
  # ⚠ SYSROM=all: this session boots with an EMPTY SOCKET and types
  # `copy /dd/sys/...` at the shell, so the demo data has to be in the ROM
  # disk.  Since 2026-09-20 it is on an SD card by default and /DD/SYS holds
  # only errmsg (software/nitros9/mkrom.sh, mksddisk.sh).
  CMDS_EXTRA="rastbar wave overworld" SYSROM=all sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { cat "$OUT/mkrom.log"; exit 1; }
fi
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c audio/refplayer/card.c
python3 $V/session.py "$OUT"

STOP=$(printf '\nDONE-arm6309')
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 SERIAL_TIMES=serial.times \
   SERIAL_STOP="$STOP" PS2_KBD="$(cat kbd.txt)" PS2_KBD_GATE="PS/2 keyboard" \
   PS2_MOUSE="$(cat mouse.txt)" PS2_MOUSE_GATE="PS/2 mouse" WILD=1 \
   ./emu arm6309_rom.bin . 600 > /dev/null 2> emu.log) || true
tail -1 "$OUT/emu.log"
grep -q "SERIAL_STOP seen" "$OUT/emu.log" || { grep -m1 -A3 "WILD\|FAIL" "$OUT/emu.log"; echo "FAIL  the session did not finish"; exit 1; }
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
if grep -n "Error #" "$OUT/console.txt"; then echo "FAIL  a command failed (build/console.txt)"; exit 1; fi

python3 $V/mkvideo.py "$OUT" "$ROOT/$V/nitros9-progress.mp4"
