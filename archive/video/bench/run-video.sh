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
  # ⚠ SYSROM=all: this session types `copy /dd/sys/...` at the shell, so the
  # demo data has to be in /DD/SYS.  It is on the card's DATA directory by
  # default (2026-09-20) and /SYS holds only errmsg; SYSROM= is what also
  # copies it to /SYS.  ⛔ AND /DD IS THE CARD SINCE 2026-09-22: mksyscard.sh
  # puts $OUT/romsys there, because the ROM has no filesystem to put it in.
  CMDS_EXTRA="rastbar wave overworld" SYSROM=all sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { cat "$OUT/mkrom.log"; exit 1; }
fi
# ⛔ THE CARD IS THE SYSTEM DISK since 2026-09-22 (arm6309 docs/history.md):
# the ROM carries the toolbox and no filesystem, so a session with an EMPTY
# SOCKET does not reach a shell at all.  mkrom.sh writes system.img beside the
# ROM out of the same build, and /DD is that card - which is why the
# `copy /dd/sys/...` lines below still read what SYSROM/$OUT/sys put there.
SDIMG="$OUT/system.img"; export SDIMG
[ -f "$SDIMG" ] || { echo "FAIL  no $SDIMG - mkrom.sh should have built the system card"; exit 1; }
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c software/demo/emu/hd6309.c audio/refplayer/card.c
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
