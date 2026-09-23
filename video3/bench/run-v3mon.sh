#!/bin/sh
# ⭐ THE BLOCK-STREAMED PLATFORM WORLD, AND WHAT IT COSTS.
#
#   sh video3/bench/run-v3mon.sh          ~25 min.  OUT=dir, FRAMES=n, MODES=...
#
# `monster` is optimizations.md's priority list, entries 1, 2 and 3, built
# as one scene: no OS call per frame (the scroll written straight at the
# card inside the blank the frame poll already waited for), a level
# streamed into the ring 384 pixels ahead of the view a column at a time,
# and 256 Floyd-Steinberg-dithered colours with a cast of eight different
# keyed-blit creatures.  mvania asked "with the card doing what the plan
# says, what can a game put on the screen?"; this asks what a game can put
# there when the level is LONGER THAN VRAM.
#
# ⭐ THE RUNS, and each is one leg of the experiment:
#
#   m0    THE SCENE - 1,050 frames (15.0 s) at 4 px a frame, twelve actors.
#         The contact sheets come from this one
#   m16   the SWEEP, 2, 4 ... 28 actors: where the frame breaks
#   m1    the same scene with the scroll through SS.SCROLL.  ⭐ Entry 8's
#         comparison: the identical twenty bits, committed by the same VBL
#         service in the same blank, for a system call
#   m2    no refill at all: what the column stream costs, held against m0
#   m128  the actors in two phases instead of interleaved
#   s2 s8 the scene at 2 and 8 px a frame, which is 7.1's refill table
#
# ⛔ AND TWO MUTATIONS, WHICH ARE WHAT MAKE THE GATE WORTH ANYTHING.  m32
# fills each column from the level column NEXT DOOR and m64 never restores
# actor 0; both are required to FAIL the VRAM compare.  A gate nobody has
# seen fail is a gate nobody has tested (CLAUDE.md).
#
# ⛔ Its exit code is the answer, and `Error #` on the console fails it.
# ⭐ CONTACT SHEETS AND NO VIDEO: a pass is reviewed from the sheets first
# (CLAUDE.md, and the demo's own rule).
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3mon}
FRAMES=${FRAMES:-1050}
SPEED=${SPEED:-4}
ACTORS=${ACTORS:-12}
MODES=${MODES:-"0 16 1 2 128"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-60}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  python3 video3/bench/mkmonster.py ../nitros9/level2/arm6309/cmds > "$OUT/mkart.log" 2>&1 || {
    cat "$OUT/mkart.log"; echo "FAIL  the art did not generate"; exit 1; }
  # ⚠ CMDS_EXTRA: since 2026-09-20 the demos are NOT in the ROM disk (they go
  # on an SD card - software/nitros9/mksddisk.sh, video3/bench/run-v3sd.sh).
  # This bench boots with an empty socket and types `monster` at /DD, so it
  # asks the recipe for that one command.  Nothing has to be given back any
  # more: the ROM disk has ~65 K free.
  CMDS_EXTRA=monster sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }
# ⛔ THE CARD IS THE SYSTEM DISK since 2026-09-22 (arm6309 docs/history.md):
# the ROM carries the toolbox and no filesystem, so a session with an EMPTY
# SOCKET does not reach a shell at all.  mkrom.sh writes system.img beside the
# ROM out of the same build, and /DD is that card - which is why the
# `copy /dd/sys/...` lines below still read what SYSROM/$OUT/sys put there.
SDIMG="$OUT/system.img"; export SDIMG
[ -f "$SDIMG" ] || { echo "FAIL  no $SDIMG - mkrom.sh should have built the system card"; exit 1; }
cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0

# run DIR MODE FRAMES SPEED ACTORS SECONDS KEEPFRAMES
run() {
  D="$OUT/$1"; m=$2; f=$3; sp=$4; na=$5; secs=$6
  rm -rf "$D"; mkdir -p "$D"
  echo "$m $f $sp $na" > "$D/args.txt"
  # ⚠ CR, not LF (demo-report.md 15.3)
  printf 'iniz w5\rmonster %d %d %d %d >/w5\recho DONE-arm6309\r' "$m" "$f" "$sp" "$na" \
    > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 VRAMDUMP=vram.bin \
     "$OUT/emu" "$OUT/arm6309_rom.bin" . "$secs" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.log" || {
    echo "FAIL  $1 did not finish"; tail -5 "$D/emu.log"; fail=1; }
  if grep -n "Error #" "$D/console.txt"; then echo "FAIL  $1: a command failed"; fail=1; fi
  # ⛔ Strip the colour first: `grep '^FAIL'` against a coloured line matches
  # nothing and reads exactly like a pass (CLAUDE.md's seventh trap).
  if sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -q '^FAIL\|^WILD'; then
    echo "FAIL  $1: the emulator objected"
    sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -m4 '^FAIL\|^WILD'; fail=1
  fi
  # ⚠ a recording is ~70 KB a frame: only the sheet run keeps one.
  [ "$1" = "m0" ] || [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
}

for m in $MODES; do
  secs=$SECONDS_OF_MACHINE
  f=$FRAMES
  [ "$m" = "16" ] && f=$((FRAMES * 2)) && secs=$((SECONDS_OF_MACHINE + 45))
  run "m$m" "$m" "$f" "$SPEED" "$ACTORS" "$secs"
done
if [ -z "$NOSPEED" ]; then
  # ⭐ 7.1's refill table, measured: a column every 8, 4 and 2 frames.  The
  # frame count is scaled so each run covers the same length of level.
  run s2 0 $((FRAMES * 2)) 2 "$ACTORS" $((SECONDS_OF_MACHINE + 45))
  run s8 0 $((FRAMES / 2)) 8 "$ACTORS" "$SECONDS_OF_MACHINE"
fi

DIRS=""
for m in $MODES; do DIRS="$DIRS $OUT/m$m"; done
[ -z "$NOSPEED" ] && DIRS="$DIRS $OUT/s2 $OUT/s8"
python3 video3/bench/checkv3mon.py $DIRS || fail=1

# ⛔ THE MUTATION TEST.  Each of these breaks one thing on purpose and the
# gate is REQUIRED to catch it; a run that passed here would mean the gate
# cannot fail, which is worse than not having one.
if [ -z "$NOMUTATE" ]; then
  echo
  echo "⛔ the mutations, which the gate has to catch:"
  MD=""
  for m in 32 64; do
    run "x$m" "$m" 300 "$SPEED" "$ACTORS" "$SECONDS_OF_MACHINE"
    MD="$MD $OUT/x$m"
  done
  NOSHEET=1 python3 video3/bench/checkv3mon.py --gate-must-fail $MD || fail=1
fi

[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the scene ran in every mode; contact sheets beside $OUT/m0"
