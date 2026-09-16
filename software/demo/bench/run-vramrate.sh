#!/bin/sh
# vramrate.asm on the host emulator: how fast a 6809 puts bytes into VRAM.
#
#   sh software/demo/bench/run-vramrate.sh [seconds]     (OUT=dir overrides)
#
# The emulator's CPU is cycle-checked against mc6809e.v (emu/test/cycles.py),
# so the phase times below are E cycles, not an approximation of them.
#
# ⚠ THE TWO RUNNERS SHARE software/demo/build/.  Do not run run-vramrate.sh and
# run-vramrate-rtl.sh at the same time: both assemble bench/vramrate.asm into
# build/vramrate.bin, and a reader can pick up a half-written one.  Same shape
# as CLAUDE.md's "one fit at a time" - verify with a rebuild and a compare if
# you ever suspect it.
set -e
cd "$(dirname "$0")/.."
ROOT=$(cd ../.. && pwd)
SECS=${1:-10}
OUT=${OUT:-/tmp/arm6309-vramrate}
B=build
mkdir -p $B "$OUT"
sh "$ROOT/software/tools/fetch-a09.sh" > /dev/null
A09="${A09_DIR:-/tmp/arm6309-a09}/a09"
"$A09" -B$B/vramrate.bin -L$B/vramrate.lst bench/vramrate.asm > $B/vramrate.log 2>&1 || { cat $B/vramrate.log; exit 1; }
if grep -qi "error" $B/vramrate.log; then cat $B/vramrate.log; exit 1; fi
python3 - "$ROOT" $B <<'PY'
import sys
root, b = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xFF" * (1 << 20))
rom[0:8192] = open(root + "/software/boot/boot.bin", "rb").read()
code = open(b + "/vramrate.bin", "rb").read()
rom[8192:8192 + len(code)] = code
open(b + "/vramrate.rom", "wb").write(rom)
PY
cc -O2 -w -I"$ROOT/audio/refplayer" -o "$OUT/emu" emu/machine.c emu/cpu6809.c "$ROOT/audio/refplayer/card.c"
"$OUT/emu" $B/vramrate.rom "$OUT" "$SECS" > "$OUT/emu.out" 2> "$OUT/emu.log" || true
python3 tools/vramrate.py "$OUT/emu.log"
