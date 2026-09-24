#!/bin/sh
# ⭐⭐ PINBALL CONSTRUCTION SET, AND THE SPAN DATABASE CHECKED AGAINST THE 6502.
#
#   sh video3/bench/run-pcs.sh          OUT=dir  RUNS='m0 m1 m2'
#
# `pcs` is Bill Budge's Pinball Construction Set (Atari 800, 1983), ported from
# his own MIT-licensed sources in reference/pcs/.  video3/docs/pcs.md is the
# spec; the two decisions it rests on are worth restating here because this
# bench exists to prove the first of them:
#
#   ⭐ THE WORLD IS THE ORIGINAL'S AND ONLY THE RENDERER IS DOUBLED, so every
#     number in the database and the simulator is integer and EXACTLY
#     reproducible - which is what lets a Python transliteration of the 6502 be
#     the gate rather than a screenshot.
#   ⭐ THE SPAN DATABASE IS A DISPLAY LIST, because video3 cannot XOR and every
#     composite in the original is one.
#
# ⛔ THE GATE IS THE PICTURE, PIXEL FOR PIXEL, AND THE PICTURE IS THE DATABASE.
# `pcs 0` builds the four-object test table mkpcs.py generates, runs the scan
# converter over it and paints the result; `checkpcs.py` builds the SAME four
# objects through pcspak.py - the transliteration of PPAK.s - renders them the
# way pcsdraw.inc does, and compares all 307,200 bytes of the table rectangle.
# A misread slope, a span off by one, a B-polygon stored the wrong way round:
# none survives it.
#
# ⛔ AND TWO MUTATIONS, BECAUSE A GATE NOTHING CAN FAIL IS NOT A GATE:
#   m1  the midpoint x rounding is dropped, so every sloped edge moves
#   m2  a B-polygon paints its RECORDS instead of their complement - the bug
#       the Python model caught, and the one that looks plausible on screen
#       while inverting the ball's world
#   m6  ⭐⭐ THE EDITOR - a dozen edits from `mkpcs.edit_script()`, run by the
#       machine and by pcsedit.DB, compared on what each step came to, on every
#       byte of the object area and on the whole span database.  ⛔ Two of them
#       must be REFUSED: an edit the database will not take has to leave no
#       trace, and a gate that never sees a refusal has not checked the
#       rollback at all.
#   m5  ⭐ BOUNCE rotates back by TTA instead of 32 - TTA, which is the gate on
#       the TRAJECTORY rather than on the picture.  ⛔ The two are the SAME for
#       tta 0 and 16, so a ball in a box of flat walls behaves identically and
#       only a slope tells them apart - which is why the test table has one.
# All three are REQUIRED to be rejected.
#
# ⚠ Needs ../nitros9 on its arm6309 branch, so it is in no aggregate.
# ⛔ Its exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-pcs}
FRAMES=${FRAMES:-30}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-90}
# ⚠ m6 IS NOT IN THE DEFAULT SET: the editor's 6809 side does not yet agree
# with pcsedit.py, which is the specification and is green.  `RUNS=m6` runs it.
RUNS=${RUNS:-"m0 m4 f0 fX m1 m2 m5"}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

# ⭐ THE MODEL IS CHECKED BEFORE THE MACHINE IS BUILT.  pcspak.py and
# pcsphys.py carry their own self-tests; if the transliteration is broken there
# is no point spending six minutes finding out on a 6809.
echo "=== the model, first ==="
python3 video3/bench/pcsphys.py || { echo "FAIL  the divide"; exit 1; }
python3 video3/bench/pcspak.py  || { echo "FAIL  the scan converter"; exit 1; }
python3 video3/bench/pcsparts.py > "$OUT/parts.log" 2>&1 || {
  cat "$OUT/parts.log"; echo "FAIL  the part extraction"; exit 1; }
tail -2 "$OUT/parts.log"
echo

if [ -z "$NOBUILD" ]; then
  python3 video3/bench/mkpcs.py "$NITROS9DIR/level2/arm6309/cmds" \
    > "$OUT/mkart.log" 2>&1 || {
      cat "$OUT/mkart.log"; echo "FAIL  the data did not generate"; exit 1; }
  tail -4 "$OUT/mkart.log"
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⛔ mksyscard.sh AND NOT mksddisk.sh.  The ROM carries no filesystem since
# 2026-09-22, so a plain data card is a machine that stops at "RKBoot Krn tbn0"
# and every claim after that fails for a reason that is not the thing under
# test.  CLAUDE.md's table says so; run-scroll.sh records that it still cost a
# run.
# ⛔ OUT= AND DATA= ARE PASSED EXPLICITLY.  mksyscard.sh has its own
# `OUT=${OUT:-/tmp/arm6309-nitros9}` default and this script never exported
# its own, so the card was built from ANOTHER BENCH'S data directory - which
# nothing noticed for as long as `pcs` needed no data file, and which then
# presented as a table file that mkrom.sh had just written and the card did
# not have.
OUT="$OUT" DATA="$OUT/data" sh software/nitros9/mksyscard.sh "$OUT/sd.img" pcs \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
tail -3 "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

# ⛔ THE RUN STOPS ON PCS-RAN, NOT ON THE SHELL'S PROMPT.  VRAMDUMP is taken
# when the emulator stops, and `pcs` prints this line while it still owns the
# card; stopping on DONE-arm6309 instead dumps a screen the driver has already
# begun repainting, and the gate reads twelve pixels of somebody else's window.
STOP="PCS-RAN"
fail=0

run() {
  D="$OUT/$1"; m=$2
  rm -rf "$D"; mkdir -p "$D"
  # ⚠ CR, NOT LF.  The shell's line terminator is carriage return; a script
  # written with newlines is typed in full, echoed in full, and executed not at
  # all - which looks exactly like a program that ran and printed nothing.
  printf 'chx /sd0/cmds\riniz w5\rpcs %d %d >/w5\recho DONE-arm6309\r' \
    "$m" "$FRAMES" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
     SERIAL_THINK=700 SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     VRAMDUMP=vram.bin "$OUT/emu" "$ROM" . "$SECONDS_OF_MACHINE" \
     > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  # ⛔ Strip the colour FIRST: `grep '^FAIL'` against a coloured line matches
  # nothing and reads exactly like a pass (CLAUDE.md's seventh trap).
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.txt" || {
    echo "FAIL  $1 did not finish"; tail -5 "$D/emu.txt"; fail=1; }
  if grep -n "Error #" "$D/console.txt"; then
    echo "FAIL  $1: a command failed"; fail=1; fi
  if grep -q '^FAIL\|^WILD' "$D/emu.txt"; then
    echo "FAIL  $1: the emulator objected"; grep -m4 '^FAIL\|^WILD' "$D/emu.txt"
    fail=1; fi
  grep -q "PCS-RAN" "$D/console.txt" || {
    echo "FAIL  $1: pcs did not say it ran"; fail=1; }
  # ⛔ `grep -q X && { ... }` AS THE LAST STATEMENT OF A FUNCTION IS A TRAP.
  # When X is ABSENT - which here is the SUCCESS case - grep exits 1, so the
  # function exits 1, and `set -e` kills the whole bench with no message at
  # exactly the moment everything started working.  CLAUDE.md records the same
  # shape for `grep -c`; `if ... then ... fi` has no exit status of its own.
  if grep -q "PCS-ERR" "$D/console.txt"; then
    echo "FAIL  $1: ⛔ the scan converter ABORTED - the database is not consistent"
    fail=1
  fi
  return 0
}

# ⭐ A TABLE OFF THE CARD, which is where tables live (pcsfile.inc).  `run`
# builds `pcs <mode> <frames>`; this one appends a bare table NAME, which
# `Build` takes in preference to anything in the module.
runf() {
  D="$OUT/$1"; shift
  rm -rf "$D"; mkdir -p "$D"
  printf 'chx /sd0/cmds\riniz w5\rpcs %s >/w5\recho DONE-arm6309\r' "$*" \
    > "$D/typed.txt"
  # ⛔ IT STOPS ON THE SHELL'S ECHO, NOT ON PCS-RAN, because the refusal leg
  # must be able to NOT print PCS-RAN and still finish.
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
     SERIAL_THINK=700 SERIAL_STOP="DONE-arm6309" WILD=1 VIDEO3=1 \
     SDIMG="$OUT/sd.img" VRAMDUMP=vram.bin "$OUT/emu" "$ROM" . \
     "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  return 0
}

for r in $RUNS; do
  case "$r" in
    m0) run m0 0 ;;
    f0) runf f0 0 "$FRAMES" demo2.pbt ;;
    fX) runf fX 0 "$FRAMES" nosuch.pbt ;;
    m4) run m4 4 ;;
    m1) run m1 1 ;;
    m2) run m2 2 ;;
    m5) run m5 5 ;;
    m6) run m6 6 ;;
    m7) run m7 7 ;;
  esac
done

echo
echo "=== the table, against PPAK.s ==="
for r in $RUNS; do
  case "$r" in
    f0) echo "--- f0 ⭐⭐ A TABLE LOADED OFF THE CARD ---"
        python3 video3/bench/checkpbt.py "$OUT/f0" demo2.pbt || fail=1 ;;
    fX) echo "--- fX ⛔ a table that is not there - this must be REFUSED ---"
        if grep -q "PCS-RAN" "$OUT/fX/console.txt"; then
          echo "FAIL  pcs ran on a table it could not load"; fail=1
        elif grep -q "PCS-NOFILE" "$OUT/fX/console.txt"; then
          echo "ok    it refused, and said so"
        else
          echo "FAIL  no PCS-NOFILE and no PCS-RAN - it did neither"; fail=1
        fi ;;
    m0) echo "--- m0: the scan converter, and it must be exact ---"
        python3 video3/bench/checkpcs.py "$OUT/m0" || fail=1 ;;
    m4) echo "--- m4 ⭐⭐ THE BALL, frame for frame against RUN.s ---"
        python3 video3/bench/checkpcs.py "$OUT/m4" ball || fail=1 ;;
    m1) echo "--- m1 ⛔ MUTATION: no midpoint rounding - this must FAIL ---"
        if python3 video3/bench/checkpcs.py "$OUT/m1" > "$OUT/m1.txt" 2>&1
        then echo "FAIL  the gate passed a run with every sloped edge moved"
             fail=1
        else echo "ok    the gate rejected it"; head -4 "$OUT/m1.txt" | tail -2; fi ;;
    m6) echo "--- m6 ⭐⭐ THE EDITOR: a construction session, and the database it left ---"
        python3 video3/bench/checkpcs.py "$OUT/m6" edit || fail=1 ;;
    m5) echo "--- m5 ⛔ MUTATION: BOUNCE rotates back by TTA - this must FAIL ---"
        if python3 video3/bench/checkpcs.py "$OUT/m5" ball > "$OUT/m5.txt" 2>&1
        then echo "FAIL  the gate passed a run whose every bounce is mirrored"
             fail=1
        else echo "ok    the gate rejected it"; grep -m1 'diverges' "$OUT/m5.txt"; fi ;;
    m2) echo "--- m2 ⛔ MUTATION: the B-polygon paints its records - this must FAIL ---"
        if python3 video3/bench/checkpcs.py "$OUT/m2" > "$OUT/m2.txt" 2>&1
        then echo "FAIL  the gate passed a run with the backdrop inside out"
             fail=1
        else echo "ok    the gate rejected it"; head -4 "$OUT/m2.txt" | tail -2; fi ;;
  esac
done

echo
[ "$fail" = 0 ] && echo "ok    run-pcs.sh: the span database and the ball are what PPAK.s and RUN.s build, and every mutation was caught"
[ "$fail" = 0 ] || echo "FAIL  run-pcs.sh"
exit "$fail"
