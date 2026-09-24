#!/bin/sh
# ⭐⭐ A WORLD OF ANY SIZE, STREAMED THROUGH THE RING - and the ring checked
# byte for byte against the invariant that makes it possible.
#
#   sh software/tilescroll/bench/run-tilescroll.sh       ~12 min.  OUT=dir, FRAMES=n
#
# `tilescroll` (software/tilescroll/docs/scrolling.md, and the port's level2/arm6309/cmds/
# tilescroll.asm) is the other answer to the problem `zelda` solves by being a
# room game.  The camera roams a 4096 x 2048 world with the hero in the middle
# of it, in VMODE 11's square 640 x 480 - and the tile bank lives in the
# 384 x 512 rectangle of ring the raster never looks at, rotating through it
# one 32-column strip at a time so that it is never in the way.
#
# ⭐ THE GATE IS THE INVARIANT, not a screenshot.  After any amount of travel
# ring column c must hold world column c (mod 1024) for the 23 slots of the
# terrain window, and the other nine must hold the bank's nine strips wherever
# the rotation has left them.  `checktilescroll.py` walks the same path the
# program walks, works out where every strip ended up, and compares all
# 524,288 bytes.  A rotation that loses a strip, a column composed from the
# wrong world tile, a band that lands a half-tile out - none survive it.
#
# ⛔ AND TWO MUTATIONS, BECAUSE A GATE NOTHING CAN FAIL IS NOT A GATE:
#   m1    the strip is not moved, so the bank walks into the world
#   m2    the vertical band is not composed, so the rows arriving at the
#         bottom of the view keep the world that was there 512 rows ago
# Both are REQUIRED to be rejected.
#
# ⛔ Its exit code is the answer.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/scroll}
FRAMES=${FRAMES:-1200}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-140}
RUNS=${RUNS:-"m0 m1 m2"}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  python3 software/tilescroll/bench/mktilescroll.py "$NITROS9DIR/level2/arm6309/cmds" \
    > "$OUT/mkart.log" 2>&1 || {
      cat "$OUT/mkart.log"; echo "FAIL  the tileset did not generate"; exit 1; }
  tail -4 "$OUT/mkart.log"
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD, and its DATA is the tile bank and nothing else - 147,456 bytes,
# where mkrom.sh's whole data set would put 800 KB of fonts and streams on a
# card this bench never reads.
# ⛔ mksyscard.sh AND NOT mksddisk.sh.  The ROM carries no filesystem, so a
# plain data card is a machine that does not start: it gets as far as
# "RKBoot Krn tbn0" and stops, and every claim afterwards fails for a reason
# that has nothing to do with the thing under test.  CLAUDE.md's table says
# this; it still cost a run here on 2026-09-23.
SD="$OUT/scrolldata"
rm -rf "$SD"; mkdir -p "$SD"
cp software/tilescroll/bench/tilescroll.bnk "$SD/"
DATA="$SD" sh software/nitros9/mksyscard.sh "$OUT/sd.img" tilescroll \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
tail -3 "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   hardware/cpu/sim/cpu6809.c hardware/cpu/sim/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0

# run NAME MODE
run() {
  D="$OUT/$1"; m=$2
  rm -rf "$D"; mkdir -p "$D"
  # ⚠ CR, NOT LF.  The shell's line terminator is carriage return; a script
  # written with newlines is typed in full, echoed in full, and executed not
  # at all - and what it looks like is a program that ran and printed nothing
  # (demo-report.md §15.3, and it cost a run here on 2026-09-23).
  printf 'chx /sd0/cmds\riniz w5\rtilescroll %d %d >/w5\recho DONE-arm6309\r' \
    "$m" "$FRAMES" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
     SERIAL_THINK=700 SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     VRAMDUMP=vram.bin "$OUT/emu" "$ROM" . "$SECONDS_OF_MACHINE" \
     > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  # ⛔ Strip the colour first: `grep '^FAIL'` against a coloured line matches
  # nothing and reads exactly like a pass (CLAUDE.md's seventh trap).
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.txt" || {
    echo "FAIL  $1 did not finish"; tail -5 "$D/emu.txt"; fail=1; }
  if grep -n "Error #" "$D/console.txt"; then
    echo "FAIL  $1: a command failed"; fail=1; fi
  if grep -q '^FAIL\|^WILD' "$D/emu.txt"; then
    echo "FAIL  $1: the emulator objected"; grep -m4 '^FAIL\|^WILD' "$D/emu.txt"
    fail=1; fi
  grep -q "SCROLL-RAN" "$D/console.txt" || {
    echo "FAIL  $1: the scene did not say it ran"; fail=1; }
}

for r in $RUNS; do
  case "$r" in
    m0) run m0 0 ;;
    m1) run m1 1 ;;
    m2) run m2 2 ;;
  esac
done

echo
echo "=== the ring against the invariant ==="
for r in $RUNS; do
  case "$r" in
    m0) echo "--- m0: the engine, and it must be exact ---"
        python3 software/tilescroll/bench/checktilescroll.py "$OUT/m0" "$FRAMES" || fail=1 ;;
    m1) echo "--- m1 ⛔ MUTATION: the strip is not moved - this must FAIL ---"
        if python3 software/tilescroll/bench/checktilescroll.py "$OUT/m1" "$FRAMES" > "$OUT/m1.txt" 2>&1
        then echo "FAIL  the gate passed a run whose bank walks into the world"
             fail=1
        else echo "ok    the gate rejected it"; head -4 "$OUT/m1.txt" | tail -2; fi ;;
    m2) echo "--- m2 ⛔ MUTATION: no vertical band - this must FAIL ---"
        if python3 software/tilescroll/bench/checktilescroll.py "$OUT/m2" "$FRAMES" > "$OUT/m2.txt" 2>&1
        then echo "FAIL  the gate passed a run with no vertical streaming"
             fail=1
        else echo "ok    the gate rejected it"; head -4 "$OUT/m2.txt" | tail -2; fi ;;
  esac
done

echo
[ "$fail" = 0 ] && echo "ok    run-tilescroll.sh: the engine is byte-exact and both mutations were caught"
[ "$fail" = 0 ] || echo "FAIL  run-tilescroll.sh"
exit "$fail"
