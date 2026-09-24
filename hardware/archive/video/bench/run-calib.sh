#!/bin/sh
# calib.asm on the whole machine: demo_tb with a ROM that measures what the
# show's model and the emulator assume about the video card.
#
#   sh software/archive/demo/bench/run-calib.sh [seconds]      (OUT=dir overrides)
#
# demo_tb's own claims about the game do not apply to this ROM and fail; the
# answers are tools/calib.py's.
set -e
cd "$(dirname "$0")/.."
ROOT=$(cd ../.. && pwd)
SECS=${1:-6}
OUT=${OUT:-/tmp/arm6309-calib}
B=build
mkdir -p $B "$OUT"
sh "$ROOT/software/tools/fetch-a09.sh" > /dev/null
A09="${A09_DIR:-/tmp/arm6309-a09}/a09"
"$A09" -B$B/calib.bin -L$B/calib.lst bench/calib.asm > $B/calib.log 2>&1 || { cat $B/calib.log; exit 1; }
if grep -qi "error" $B/calib.log; then cat $B/calib.log; exit 1; fi
python3 - "$ROOT" $B <<'PY'
import sys
root, b = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xFF" * (1 << 20))
rom[0:8192] = open(root + "/software/boot/boot.bin", "rb").read()
code = open(b + "/calib.bin", "rb").read()
rom[8192:8192 + len(code)] = code
open(b + "/calib.hex", "w").write("".join(f"{x:02x}\n" for x in rom))
PY
V="$ROOT/hardware/tools/sim"
if [ ! -x "$V/obj_demo/demo_tb" ]; then
  echo "FAIL  build demo_tb first: sh hardware/gal/verilog/run-demo.sh" ; exit 1
fi
"$V/obj_demo/demo_tb" +out="$OUT" +secs="$SECS" +rom="$ROOT/software/archive/demo/$B/calib.hex" > "$OUT/demo.log" 2>&1 || true
python3 tools/calib.py "$OUT"
