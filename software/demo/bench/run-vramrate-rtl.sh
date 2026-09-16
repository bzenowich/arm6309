#!/bin/sh
# vramrate.asm on the WHOLE MACHINE (demo_tb): the same eight phases with a
# real mc6809e, a real video card and a real /WAIT.
#
#   sh software/demo/bench/run-vramrate-rtl.sh [seconds]    (~15 min at 7 s)
#
# demo_tb's own claims are about the show and fail on this ROM; the answer is
# tools/vramrate.py's, read off the same progress-port lines the emulator
# prints.  Needs demo_tb built: sh hardware/gal/verilog/run-demo.sh
#
# ⚠ THE TWO RUNNERS SHARE software/demo/build/.  Do not run run-vramrate.sh and
# run-vramrate-rtl.sh at the same time: both assemble bench/vramrate.asm into
# build/vramrate.bin, and a reader can pick up a half-written one.  Same shape
# as CLAUDE.md's "one fit at a time" - verify with a rebuild and a compare if
# you ever suspect it.
set -e
cd "$(dirname "$0")/.."
ROOT=$(cd ../.. && pwd)
SECS=${1:-7}
OUT=${OUT:-/tmp/arm6309-vramrate-rtl}
B=build
mkdir -p $B "$OUT"
sh "$ROOT/software/tools/fetch-a09.sh" > /dev/null
A09="${A09_DIR:-/tmp/arm6309-a09}/a09"
"$A09" -B$B/vramrate.bin -L$B/vramrate.lst bench/vramrate.asm > $B/vramrate.log 2>&1 || { cat $B/vramrate.log; exit 1; }
python3 - "$ROOT" $B <<'PY'
import sys
root, b = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xFF" * (1 << 20))
rom[0:8192] = open(root + "/software/boot/boot.bin", "rb").read()
code = open(b + "/vramrate.bin", "rb").read()
rom[8192:8192 + len(code)] = code
open(b + "/vramrate.hex", "w").write("".join(f"{x:02x}\n" for x in rom))
PY
V="$ROOT/hardware/gal/verilog"
[ -x "$V/obj_demo/demo_tb" ] || { echo "FAIL  build demo_tb first: sh hardware/gal/verilog/run-demo.sh"; exit 1; }
"$V/obj_demo/demo_tb" +out="$OUT" +secs="$SECS" +rom="$ROOT/software/demo/$B/vramrate.hex" > "$OUT/demo.log" 2>&1 || true
echo "DONE=$?" >> "$OUT/demo.log"
python3 tools/vramrate.py "$OUT/demo.log"
