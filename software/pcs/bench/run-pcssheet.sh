#!/bin/sh
# run-pcssheet.sh - every shipped table, painted by the card, on one sheet.
#
#   sh software/pcs/bench/run-pcssheet.sh          OUT=dir  BATCH=6
#
# ⭐ WHY IT IS BATCHED.  All 26 tables at once is 32 KB of object area in a
# module that already carries the art, the templates and the span database, and
# `pcs` then fails to fork with E$MemFul - a machine that boots perfectly and
# prints `Error #207`.  So the ROM is rebuilt per batch with PCSTBLS selecting
# the slice, and `pcs 7` is always the first table OF THAT BATCH.
#
# ⚠ Each run gets its OWN COPY of the card image.  Six emulators sharing one
# file is six machines writing one disk, and nothing about the resulting sheet
# would be trustworthy.
#
# ⚠ Needs ../nitros9 on its arm6309 branch, so it is in no aggregate.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -eu
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
NITROS9DIR=${NITROS9DIR:-$ROOT/../nitros9}
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/pcssheet}
BATCH=${BATCH:-6}
SECS=${SECS:-90}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

N=$(python3 -c "import sys;sys.path.insert(0,'hardware/video3/bench');import pcsfile;print(len(pcsfile.demo_tables()))")
[ "$N" -gt 0 ] || { echo "no tables - the disk images are not in reference/"; exit 1; }
echo "=== $N tables, $BATCH to a ROM ==="

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   hardware/cpu/sim/cpu6809.c hardware/cpu/sim/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

# FIRST= re-does only the tables from that index on.
i=${FIRST:-0}
while [ "$i" -lt "$N" ]; do
  j=$((i + BATCH - 1)); [ "$j" -ge "$N" ] && j=$((N - 1))
  echo "--- tables $i..$j ---"
  PCSTBLS="$i-$j" python3 software/pcs/bench/mkpcs.py "$NITROS9DIR/level2/arm6309/cmds" \
    > "$OUT/mkart.log" 2>&1 || { cat "$OUT/mkart.log"; exit 1; }
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; exit 1; }
  # ⛔ OUT= and DATA= explicitly - see run-pcs.sh.
  OUT="$OUT" DATA="$OUT/data" sh software/nitros9/mksyscard.sh "$OUT/sd.img" pcs pcsed pcsui pcsfl \
    > "$OUT/mkcard.log" 2>&1 || {
    tail -20 "$OUT/mkcard.log"; exit 1; }

  k=$i
  while [ "$k" -le "$j" ]; do
    m=$((7 + k - i)); D="$OUT/t$k"
    rm -rf "$D"; mkdir -p "$D"; cp "$OUT/sd.img" "$D/sd.img"
    printf 'chx /sd0/cmds\riniz w5\rpcs %d 30 >/w5\recho DONE-arm6309\r' "$m" \
      > "$D/typed.txt"
    ( cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
        SERIAL_THINK=700 SERIAL_STOP="PCS-RAN" WILD=1 VIDEO3=1 SDIMG="$D/sd.img" \
        VRAMDUMP=vram.bin "$OUT/emu" "$OUT/arm6309_rom.bin" . "$SECS" \
        >/dev/null 2>emu.log
      tr -d '\000\r' < serial.out > console.txt
      # ⛔ THE MARKER IS WRITTEN WHATEVER HAPPENS, so the wait below is bounded
      # by the emulator's own machine-second limit rather than by hope.
      grep -q PCS-RAN console.txt && echo "ok $k" > done || echo "FAIL $k" > done
    ) &
    k=$((k + 1))
  done
  wait
  k=$i
  while [ "$k" -le "$j" ]; do cat "$OUT/t$k/done"; k=$((k + 1)); done
  i=$((j + 1))
done

echo
python3 software/pcs/bench/pcssheet.py "$OUT" "$OUT/tables.png"
