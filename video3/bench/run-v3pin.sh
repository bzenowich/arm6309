#!/bin/sh
# ⭐ THE PINBALL TABLE, AND WHAT IT COSTS.
#
#   sh video3/bench/run-v3pin.sh          ~12 min.  OUT=dir, FRAMES=n, MODES=...
#
# `pinball` is optimizations.md §10 built: a 640 x 512 table - 327 KB of the
# card's 512 KB ring - with VSCROLL following the ball for one register pair a
# frame written inside the blank, the ball on the hardware sprite, extra balls
# as keyed blits with SAVE-BEHIND, flippers PRE-COMPOSED over their own
# background, and ⭐ the lamps and the six-digit score as PALETTE WRITES.
#
# `mvania` asked what a game can put on a screen when the room is in VRAM and
# `monster` what it can when the level is longer than VRAM.  This asks what
# happens when the WHOLE WORLD is in VRAM and nothing streams at all - which
# is the case where the card's scroll is free and its LUT does the work.
#
# ⭐ THE RUNS, and each is one leg of the experiment:
#
#   m0    THE SCENE - 1,050 frames (15.0 s), three balls.  The contact sheets
#         and the VRAM gate come from this one
#   m16   the SWEEP, 1, 2, 3 ... 15 balls: where the frame breaks
#   m1    the same scene with the scroll through SS.SCROLL.  ⭐ Entry 8's
#         comparison, measured on a third scene
#   m2    no palette writes at all: what the lamps and the scoreboard cost,
#         and ⛔ THE LAMP GATE'S NEGATIVE CONTROL - with the LUT left alone
#         not one lamp may light, which is what says the gate can fail
#   m128  the flippers re-blitted every frame: what pre-composition saves
#
# ⛔ AND TWO MUTATIONS, WHICH ARE WHAT MAKE THE GATE WORTH ANYTHING.  m32
# takes each ball's save-behind from one row BELOW where it draws, and m64
# never restores blit ball 1; both are required to FAIL the VRAM compare.  A
# gate nobody has seen fail is a gate nobody has tested (CLAUDE.md).
#
# ⚠ THE ROM DISK IS FULL.  488 K of it, 6,656 bytes free, and `pinball` is
# 35 K - so this script asks the recipe for its command and gives back the
# room (CMDS_EXTRA / CMDS_DROP, recipes/arm6309/arm6309.mak).  It deletes
# romdisk.dsk on the way in AND on the way out, because the recipe's disk rule
# depends on the module files and not on the list of them: without that, the
# next ordinary build would keep this one's shortened disk.
#
# ⛔ Its exit code is the answer, and `Error #` on the console fails it.
# ⭐ CONTACT SHEETS AND NO VIDEO: a pass is reviewed from the sheets first.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3pin}
SHEETS=${SHEETS:-$ROOT/video3/bench/pinball-sheets}
FRAMES=${FRAMES:-1050}
BALLS=${BALLS:-3}
MODES=${MODES:-"0 16 1 2 128"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-75}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
mkdir -p "$OUT"

# ⚠ BOTH ENDS.  On the way out the disk goes too, so the next `run-v3.sh` or
# `run-v3mon.sh` rebuilds a full one.
cleanup() { rm -f "$REC/romdisk.dsk" "$REC/arm6309_rom.bin"; }
trap cleanup EXIT

if [ -z "$NOBUILD" ]; then
  python3 video3/bench/mkpinball.py ../nitros9/level2/arm6309/cmds > "$OUT/mkart.log" 2>&1 || {
    cat "$OUT/mkart.log"; echo "FAIL  the art did not generate"; exit 1; }
  tail -4 "$OUT/mkart.log"
  rm -f "$REC/romdisk.dsk" "$REC/arm6309_rom.bin"
  V3=1 CMDS_EXTRA=pinball CMDS_DROP="monster mvania ded dcheck debug" \
    sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }
cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0

# run DIR MODE FRAMES BALLS SECONDS
run() {
  D="$OUT/$1"; m=$2; f=$3; nb=$4; secs=$5
  rm -rf "$D"; mkdir -p "$D"
  echo "$m $f $nb" > "$D/args.txt"
  # ⚠ CR, not LF (demo-report.md §15.3)
  printf 'iniz w5\rpinball %d %d %d >/w5\recho DONE-arm6309\r' "$m" "$f" "$nb" \
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
  # ⚠ a recording is ~70 KB a frame, so only two runs keep one: the scene,
  # which the sheets and the lamp gate come from, and ⛔ m2, which is the
  # lamp gate's NEGATIVE CONTROL and can only be judged from a picture.
  case "$1" in m0|m2) ;; *) [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin";; esac
}

for m in $MODES; do
  secs=$SECONDS_OF_MACHINE
  f=$FRAMES
  [ "$m" = "16" ] && f=$((FRAMES * 2)) && secs=$((SECONDS_OF_MACHINE + 45))
  run "m$m" "$m" "$f" "$BALLS" "$secs"
done

DIRS=""
for m in $MODES; do DIRS="$DIRS $OUT/m$m"; done
SHEETDIR="$SHEETS" python3 video3/bench/checkv3pin.py $DIRS || fail=1

# ⛔ THE MUTATION TEST.  Each of these breaks one thing on purpose and the gate
# is REQUIRED to catch it; a run that passed here would mean the gate cannot
# fail, which is worse than not having one.
if [ -z "$NOMUTATE" ]; then
  echo
  echo "⛔ the mutations, which the gate has to catch:"
  MD=""
  for m in 32 64; do
    run "x$m" "$m" 300 "$BALLS" "$SECONDS_OF_MACHINE"
    MD="$MD $OUT/x$m"
  done
  NOSHEET=1 python3 video3/bench/checkv3pin.py --gate-must-fail $MD || fail=1
fi

# ⚠ /tmp is where the recordings are and they are hundreds of megabytes.  The
# sheets and the logs are what is kept.
[ -n "$KEEPFRAMES" ] || rm -f "$OUT"/*/frames.bin

[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the table ran in every mode; contact sheets in $SHEETS"
