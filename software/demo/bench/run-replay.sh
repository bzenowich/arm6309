#!/bin/sh
# The 6809 replayer against audio/refplayer, on the CPU alone - replay_tb.sv.
#
#   sh software/demo/bench/run-replay.sh [seconds]
#
# EXIT CODE IS THE ANSWER: 0 only if both register traces are identical over
# the whole run and the sample RAM the 6809 loader uploaded is byte for byte
# what refplayer's loader produces.
set -e
cd "$(dirname "$0")/.."
ROOT=$(cd ../.. && pwd)
SECS=${1:-40}
B=build
V="verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --timescale 1ns/1ps"
$V --top-module replay_tb -Mdir $B/obj_replay \
   "$ROOT/hardware/vendor/mc6809/mc6809e.v" "$ROOT/hardware/vendor/mc6809/mc6809i.v" \
   bench/replay_tb.sv -o replay_tb > $B/replay_build.log 2>&1 || { tail -20 $B/replay_build.log; exit 1; }

# refplayer: its trace for SECS seconds, and the tick count it reached
"$ROOT/build-host/refplayer" --trace $B/ref.trace --sram $B/ref.sram --seconds "$SECS" $B/demo.mod > /dev/null
TICKS=$(tail -1 $B/ref.trace | awk '{print $1+0}')

$B/obj_replay/replay_tb +rom=$B/rom.hex +trace=$B/replay.trace +sram=$B/replay.sram +ticks=$((TICKS + 1))

# compare through the last tick both reached
awk -v t="$TICKS" '$1+0 <= t' $B/replay.trace > $B/replay.cmp
awk -v t="$TICKS" '$1+0 <= t' $B/ref.trace > $B/ref.cmp
fail=0
if cmp -s $B/replay.cmp $B/ref.cmp; then
  echo "ok    the 6809 replayer's register trace is refplayer's, byte for byte: $(wc -l < $B/ref.cmp) writes over $TICKS ticks"
else
  echo "FAIL  the traces differ - first difference:"
  diff $B/ref.cmp $B/replay.cmp | head -12
  fail=1
fi
if cmp -s $B/replay.sram $B/ref.sram; then
  echo "ok    the sample RAM the 6809 uploaded is refplayer's loader's, $(wc -l < $B/ref.sram) bytes"
else
  echo "FAIL  the sample RAM differs:"
  diff $B/ref.sram $B/replay.sram | head -6
  fail=1
fi
exit $fail
