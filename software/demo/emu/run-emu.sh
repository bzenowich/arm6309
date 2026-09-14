#!/bin/sh
# The demo ROM on the host emulator, and the same checks and video as the RTL run.
#
#   sh software/demo/emu/run-emu.sh [seconds]        OUT=dir overrides /tmp/arm6309-emu
#
# Seconds of wall clock for the whole show. ⚠ NOT THE MACHINE - machine.c says
# what it models; hardware/gal/verilog/run-demo.sh is the run that counts.
set -e
cd "$(dirname "$0")/.."
SECS=${1:-90}
OUT=${OUT:-/tmp/arm6309-emu}
mkdir -p "$OUT"
[ -n "$NOBUILD" ] || sh build.sh > "$OUT/build.log" 2>&1 || { tail -20 "$OUT/build.log"; exit 1; }
cc -O2 -Wall -I../../audio/refplayer -o "$OUT/emu" emu/machine.c emu/cpu6809.c ../../audio/refplayer/card.c
"$OUT/emu" build/rom.bin "$OUT" "$SECS" 2> "$OUT/emu.log" || { tail "$OUT/emu.log"; exit 1; }
tail -1 "$OUT/emu.log"
[ -n "$VIDEO" ] || exit 0
# the sound: card.c fed the emulator's register writes at their colour clocks
ROOT=$(cd ../.. && pwd)
cc -O2 -w -I"$ROOT/audio/refplayer" -o "$OUT/tracewav" tools/tracewav.c \
   "$ROOT/audio/refplayer/card.c" "$ROOT/audio/refplayer/mod_load.c" "$ROOT/audio/refplayer/render.c" -lm
"$OUT/tracewav" "$OUT/emu.wav" build/demo.mod "$OUT/card.times"
python3 tools/mkvideo.py "$OUT" "$OUT/emu.mp4" --web --wav "$OUT/emu.wav"
