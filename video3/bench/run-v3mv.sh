#!/bin/sh
# ⭐ THE METROIDVANIA SCENE, AND WHAT IT COSTS.
#
#   sh video3/bench/run-v3mv.sh            OUT=dir overrides, FPS=n the step
#
# video3/docs/keyed-copy.md §6.3 says a metroidvania is this card's natural
# genre and that the binding constraint was the per-copy cost, which
# optimizations.md entry 4 took from 698 µs to 344.  `mvania` is the scene
# that answers what the machine does with that: a 1024 × 240 room at ring
# rows 0-239 with a clean copy at 240-479, the view scrolled over it by
# HSCROLL and VSCROLL with no refill, the hero on the card's ONE hardware
# sprite, and every other actor drawn with the span writer's sprite WMODE
# and undrawn with a copy from the clean page.
#
# ⭐ FOUR RUNS, WHICH ARE THE EXPERIMENT.  Each sweeps the actor count 2, 4
# ... 28 and marks every phase of every frame at $FF2E, which the emulator
# timestamps into marks.txt:
#
#   m0   merged restores, issued from the CARD'S OWN REGISTERS
#   m1   one rectangle an actor, the same registers - what the merge saved
#   m2   merged restores through SS.CopyN, the public path
#   m4   no restores at all - the control that prices the restores
#   m9   one rectangle an actor, and the scroll written straight at the
#        card instead of through SS.Batch: what the OS call costs
#
# ⛔ Its exit code is the answer, and `Error #` on the console fails it.
# ⭐ AND THE CORRECTNESS GATE IS THE VRAM DUMP, not the timings: the scene
# ends by restoring every actor, and the live page must then equal the clean
# page byte for byte.  One pixel left behind by the merge fails it, where a
# timing run would call the same frame a good measurement.
# ⭐ It writes CONTACT SHEETS (OUT/m0/sheet-*.png) and no video: a pass is
# reviewed from the sheets first (CLAUDE.md, and the demo's own rule).
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3mv}
FPS=${FPS:-45}
MODES=${MODES:-"0 1 2 3 4 9"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-300}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }
cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
FIRST=$(echo $MODES | awk '{print $1}')
fail=0
for m in $MODES; do
  D="$OUT/m$m"
  rm -rf "$D"; mkdir -p "$D"
  # ⚠ CR, not LF (demo-report.md §15.3).  The merge's fixed cost is the third
  # argument: 1393 bytes is 344 µs / 0.247 µs a byte, SS.CopyN's figure.
  printf 'iniz w5\rmvania %d %d %d >/w5\recho DONE-arm6309\r' "$m" "$FPS" "${FIX:-1393}" \
    > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 VRAMDUMP=vram.bin \
     "$OUT/emu" "$OUT/arm6309_rom.bin" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.log" || {
    echo "FAIL  mode $m did not finish"; tail -5 "$D/emu.log"; fail=1; }
  # ⛔ Strip the colour first: bun and the emulator both write escapes, and
  # `grep '^FAIL'` against a coloured line matches nothing and reads like a
  # pass (CLAUDE.md's seventh trap).
  if grep -n "Error #" "$D/console.txt"; then echo "FAIL  mode $m: a command failed"; fail=1; fi
  if sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -q '^FAIL\|^WILD'; then
    echo "FAIL  mode $m: the emulator objected"
    sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -m4 '^FAIL\|^WILD'; fail=1
  fi
  # ⚠ A recording is ~90 KB a frame and a sweep is ~1,400 of them, so four
  # modes is half a gigabyte for three pictures nobody looks at: the sheets
  # come from the FIRST mode and the other three are read for their MARKS.
  # KEEPFRAMES=1 keeps them all.
  [ "$m" = "$FIRST" ] || [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
done

# ⭐ One call, with the modes in order: checkv3mv.py makes the contact sheets
# for the FIRST directory it is given and the tables for all of them.
DIRS=""
for m in $MODES; do DIRS="$DIRS $OUT/m$m"; done
python3 video3/bench/checkv3mv.py $DIRS || fail=1
[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the scene ran in every mode; contact sheets beside $OUT/m$(echo $MODES | awk '{print $1}')"
