#!/bin/sh
# ⭐⭐ PINBALL CONSTRUCTION SET, AND THE SPAN DATABASE CHECKED AGAINST THE 6502.
#
#   sh software/pcs/bench/run-pcs.sh          OUT=dir  RUNS='m0 m1 m2'
#
# `pcs` is Bill Budge's Pinball Construction Set (Atari 800, 1983), ported from
# his own MIT-licensed sources in software/pcs/reference/pcs-source/.  software/pcs/docs/pcs.md is the
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
#   e0  ⭐⭐ THE EDITOR WITH A MOUSE - `pcs 23`, EdLoop, driven by
#       scripts/pcsedit.ps2.  Every gesture's fifteen-byte record against what
#       checkpcs.py works out from the SCRIPT'S points alone, then the object
#       area, the span database and the whole table's picture - and ⛔ the same
#       recording against a mutated script, which must fail.
#   e2  ⭐ THE MAGNIFIER - `pcs 23` driven by scripts/pcsmag.ps2: every
#       gesture's record against pcsmag.py, the free-hand layer MgDump streams,
#       the table with the layer composed in, the box, and every fat bit.
#   c0  ⭐ e0 AND e2 AGAIN, GESTURE AFTER GESTURE - their scripts with every
#   c2    `at` pulled in to 0.3 of its time, so each gesture starts while the
#       repaint of the last one is still running, and the press lands in it.
#       The same checks as e0 and e2 - every record, the table, the layer - and
#       ⛔ a minimum on the samples that came off pcsin.inc's mouse queue, so a
#       leg that happened to fall between repaints cannot pass as this one.
#   cX  ⛔ c0's script on `pcs 25`, which is mode 23 with the queue switched
#       off - REQUIRED to fail, or c0 would be passing for some other reason.
#   w0  ⭐ WORLD - `pcs 23` driven by scripts/pcsworld.ps2: every slider
#       dragged (past the top, past the bottom, and between), a miss, QUIT and
#       the panel again; every record against pcsworld.py, the wset EditW
#       dumps, and the panel left up so every knob position is read off the card.
#   f1  ⭐ demo2 with a layer in its file's trailer, loaded and composed.
#   d0  ⭐⭐ SAVE AND LOAD - `pcs 23 N demo2l.pbt` driven by scripts/pcsdisk.ps2
#       on its OWN copy of the card: a table edited and SAVEd twice over one
#       name, another picked off the catalogue and LOADed, a name that is not
#       there refused, and the saved one LOADed back.  Every record against
#       pcsdisk.py, the table the session ended on, and ⭐ every `.pbt` read
#       back out of the card the machine left, byte for byte.
#   m5  ⭐ BOUNCE rotates back by TTA instead of 32 - TTA, which is the gate on
#       the TRAJECTORY rather than on the picture.  ⛔ The two are the SAME for
#       tta 0 and 16, so a ball in a box of flat walls behaves identically and
#       only a slope tells them apart - which is why the test table has one.
# All three are REQUIRED to be rejected.
#
# ⚠ Needs ../nitros9 on its arm6309 branch, so it is in no aggregate.
# ⛔ Its exit code is the answer.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/pcs}
FRAMES=${FRAMES:-30}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-90}
RUNS=${RUNS:-"m0 m4 m6 e0 e1 e2 w0 c0 c2 cX d0 k0 f0 f1 fX m1 m2 m5"}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

# ⭐ THE MODEL IS CHECKED BEFORE THE MACHINE IS BUILT.  pcspak.py and
# pcsphys.py carry their own self-tests; if the transliteration is broken there
# is no point spending six minutes finding out on a 6809.
echo "=== the model, first ==="
python3 software/pcs/bench/pcsphys.py || { echo "FAIL  the divide"; exit 1; }
python3 software/pcs/bench/pcspak.py  || { echo "FAIL  the scan converter"; exit 1; }
python3 software/pcs/bench/pcskit.py || { echo "FAIL  the kit panel"; exit 1; }
python3 software/pcs/bench/pcsparts.py > "$OUT/parts.log" 2>&1 || {
  cat "$OUT/parts.log"; echo "FAIL  the part extraction"; exit 1; }
tail -2 "$OUT/parts.log"
echo

if [ -z "$NOBUILD" ]; then
  python3 software/pcs/bench/mkpcs.py "$NITROS9DIR/level2/arm6309/cmds" \
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
# test.  CLAUDE.md's table says so; run-tilescroll.sh records that it still cost a
# run.
# ⛔ OUT= AND DATA= ARE PASSED EXPLICITLY.  mksyscard.sh has its own
# `OUT=${OUT:-software/nitros9/build/rom}` default and this script never exported
# its own, so the card was built from ANOTHER BENCH'S data directory - which
# nothing noticed for as long as `pcs` needed no data file, and which then
# presented as a table file that mkrom.sh had just written and the card did
# not have.
# ⛔ AND THE FOUR LIBRARIES WITH IT: pcs is a core that F$Loads pcsed, pcsui,
# pcsfl and pcsmg out of its execution directory (pcscore.inc), and a card with pcs
# alone answers PCS-NOLIB before the first table is read.
OUT="$OUT" DATA="$OUT/data" sh software/nitros9/mksyscard.sh "$OUT/sd.img" pcs pcsed pcsui pcsfl pcsmg \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
tail -3 "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   hardware/cpu/sim/cpu6809.c hardware/cpu/sim/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

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

# ⭐⭐ THE EDITOR, DRIVEN: `pcs 23` with a PS/2 script for a hand.  ⚠ Time zero is
# PCS-EDIT - printed once the screen is up - so the script is timed against the
# editor and not against the boot.  The frame budget is EdLoop's bound; the
# script ends with `q` well inside it.
EFRAMES=${EFRAMES:-9000}
ESECONDS=${ESECONDS:-240}
# ⭐ A FOURTH ARGUMENT is a table name off the card, and $CARD the image the
# leg runs on - its own copy, for a leg that writes to it.
rune() {
  D="$OUT/$1"; m=$2; script=$3; tbl=${4:-}
  rm -rf "$D"; mkdir -p "$D"
  card=${CARD:-$OUT/sd.img}
  printf 'chx /sd0/cmds\riniz w5\rpcs %d %d %s>/w5\recho DONE-arm6309\r' \
    "$m" "$EFRAMES" "${tbl:+$tbl }" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
     SERIAL_THINK=700 SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$card" \
     PS2_SCRIPT="$script" PS2_SCRIPT_GATE=PCS-EDIT \
     VRAMDUMP=vram.bin "$OUT/emu" "$ROM" . "$ESECONDS" \
     > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.txt" || {
    echo "FAIL  $1 did not finish"; tail -5 "$D/emu.txt"; fail=1; }
  if grep -q '^FAIL\|^WILD' "$D/emu.txt"; then
    echo "FAIL  $1: the emulator objected"; grep -m4 '^FAIL\|^WILD' "$D/emu.txt"
    fail=1; fi
  for t in PCS-EDIT PCS-RAN; do
    grep -q "$t" "$D/console.txt" || { echo "FAIL  $1: pcs never said $t"; fail=1; }
  done
  return 0
}

# ⭐ A TABLE OFF THE CARD, which is where tables live (pcsfile.inc).  `run`
# builds `pcs <mode> <frames>`; this one appends a bare table NAME, which
# `Build` takes in preference to anything in the module.
runf() {
  D="$OUT/$1"; shift
  # ⛔ A LEG THAT EXPECTS PCS TO RUN STOPS ON PCS-RAN, like `run` - while pcs
  # still owns the card.  f0 stopped on the shell's echo, AFTER pcs had exited,
  # and the driver's repaint of the top-left corner was in the dump: 416 pixels
  # of colour 27 that checkpbt.py's part-art tolerance waved through, and that
  # vanished the day pcs's exit got slower.  Only fX, which must NOT print
  # PCS-RAN, needs the echo.
  FSTOP=$1; shift
  rm -rf "$D"; mkdir -p "$D"
  printf 'chx /sd0/cmds\riniz w5\rpcs %s >/w5\recho DONE-arm6309\r' "$*" \
    > "$D/typed.txt"
  # ⚠ FSTOP is DONE-arm6309 only for the refusal leg, which must be able to NOT
  # print PCS-RAN and still finish.
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 \
     SERIAL_THINK=700 SERIAL_STOP="$FSTOP" WILD=1 VIDEO3=1 \
     SDIMG="$OUT/sd.img" VRAMDUMP=vram.bin "$OUT/emu" "$ROM" . \
     "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  return 0
}

# ⭐ A SCRIPT WITH ITS GESTURES PULLED TOGETHER: every `at T` becomes
# 1 + (T - 1) * 0.3, and the `+` steps inside a gesture are left alone - so a
# drag is still a drag, and the next one starts about when this one's repaint
# does.
fast() {
  awk '$1 == "at" { $2 = sprintf("%.3f", 1 + ($2 - 1) * 0.3) } { print }' \
    "$ROOT/software/pcs/bench/scripts/$1"
}

for r in $RUNS; do
  case "$r" in
    m0) run m0 0 ;;
    f0) runf f0 PCS-RAN 0 "$FRAMES" demo2.pbt ;;
    f1) runf f1 PCS-RAN 0 "$FRAMES" demo2l.pbt ;;
    fX) runf fX DONE-arm6309 0 "$FRAMES" nosuch.pbt ;;
    m4) run m4 4 ;;
    m1) run m1 1 ;;
    m2) run m2 2 ;;
    m5) run m5 5 ;;
    m6) run m6 6 ;;
    k0) run k0 22 ;;
    e0) rune e0 23 "$ROOT/software/pcs/bench/scripts/pcsedit.ps2" ;;
    e1) python3 software/pcs/bench/scripts/mkpcsbuild.py \
          > software/pcs/bench/scripts/pcsbuild.ps2
        EFRAMES=20000 ESECONDS=340 rune e1 24 "$ROOT/software/pcs/bench/scripts/pcsbuild.ps2" ;;
    e2) ESECONDS=200 rune e2 23 "$ROOT/software/pcs/bench/scripts/pcsmag.ps2" ;;
    w0) ESECONDS=120 rune w0 23 "$ROOT/software/pcs/bench/scripts/pcsworld.ps2" ;;
    c0) fast pcsedit.ps2 > "$OUT/c0.ps2"
        ESECONDS=120 rune c0 23 "$OUT/c0.ps2" ;;
    c2) fast pcsmag.ps2 > "$OUT/c2.ps2"
        ESECONDS=120 rune c2 23 "$OUT/c2.ps2" ;;
    cX) fast pcsedit.ps2 > "$OUT/cX.ps2"
        ESECONDS=120 rune cX 25 "$OUT/cX.ps2" ;;
    d0) mkdir -p "$OUT/d0.card"; cp "$OUT/sd.img" "$OUT/d0.card/sd.img"
        CARD="$OUT/d0.card/sd.img" ESECONDS=240 \
          rune d0 23 "$ROOT/software/pcs/bench/scripts/pcsdisk.ps2" demo2l.pbt ;;
    m7) run m7 7 ;;
  esac
done

# ⛔⛔ A MUTATION LEG MUST PROVE THE CHECKER RAN.  Written as a bare
# `if python3 ... then FAIL else ok`, a checker that CRASHES exits non-zero and
# reads exactly like a caught mutation - and on 2026-09-23 an AttributeError in
# render_table made all three legs report `ok` while checking nothing at all.
# CLAUDE.md's own trap: "a negated claim that can only be satisfied by the thing
# under test EXISTING must prove the tool ran".  A real rejection prints a FAIL
# line; a crash prints a traceback and no FAIL.
mutation() {
  m=$1; what=$2; shift 2
  if python3 software/pcs/bench/checkpcs.py "$OUT/$m" "$@" > "$OUT/$m.txt" 2>&1; then
    echo "FAIL  the gate passed a run with $what"
    return 1
  fi
  if grep -q "Traceback" "$OUT/$m.txt"; then
    echo "FAIL  ⛔ the CHECKER crashed - this leg proved nothing"
    tail -3 "$OUT/$m.txt"
    return 1
  fi
  if ! grep -q "^FAIL" "$OUT/$m.txt"; then
    echo "FAIL  ⛔ non-zero exit but no FAIL line - the checker did not reject it"
    tail -3 "$OUT/$m.txt"
    return 1
  fi
  echo "ok    the gate rejected it"
  grep -m1 "^FAIL" "$OUT/$m.txt"
  return 0
}

echo
echo "=== the table, against PPAK.s ==="
for r in $RUNS; do
  case "$r" in
    f0) echo "--- f0 ⭐⭐ A TABLE LOADED OFF THE CARD ---"
        python3 software/pcs/bench/checkpbt.py "$OUT/f0" demo2.pbt || fail=1 ;;
    f1) echo "--- f1 ⭐ A TABLE WITH A FREE-HAND LAYER, loaded off the card ---"
        python3 software/pcs/bench/checkpbt.py "$OUT/f1" demo2l.pbt || fail=1 ;;
    fX) echo "--- fX ⛔ a table that is not there - this must be REFUSED ---"
        if grep -q "PCS-RAN" "$OUT/fX/console.txt"; then
          echo "FAIL  pcs ran on a table it could not load"; fail=1
        elif grep -q "PCS-NOFILE" "$OUT/fX/console.txt"; then
          echo "ok    it refused, and said so"
        else
          echo "FAIL  no PCS-NOFILE and no PCS-RAN - it did neither"; fail=1
        fi ;;
    m0) echo "--- m0: the scan converter, and it must be exact ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/m0" || fail=1 ;;
    m4) echo "--- m4 ⭐⭐ THE BALL, frame for frame against RUN.s ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/m4" ball || fail=1 ;;
    m1) echo "--- m1 ⛔ MUTATION: no midpoint rounding - this must FAIL ---"
        mutation m1 "every sloped edge moved" || fail=1 ;;
    m6) echo "--- m6 ⭐⭐ THE EDITOR: a construction session, and the database it left ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/m6" edit || fail=1 ;;
    e0) echo "--- e0 ⭐⭐ THE EDITOR WITH A MOUSE: every gesture, and the table it left ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/e0" ui \
          software/pcs/bench/scripts/pcsedit.ps2 || fail=1
        # ⛔ AND THE SAME RECORDING AGAINST A SCRIPT THAT DRAGGED BMP1 FOUR CARD
        # PIXELS FURTHER, which is REQUIRED to fail - on the records, by name.
        # A checker that models the session from the script has to be shown to
        # read the script, or it could be agreeing with the machine about
        # anything.
        sed 's/^+0.300      move to 108 152/+0.300      move to 112 152/' \
          software/pcs/bench/scripts/pcsedit.ps2 > "$OUT/e0/mutant.ps2"
        if cmp -s software/pcs/bench/scripts/pcsedit.ps2 "$OUT/e0/mutant.ps2"; then
          echo "FAIL  the e0 mutation changed nothing"; fail=1
        elif python3 software/pcs/bench/checkpcs.py "$OUT/e0" ui "$OUT/e0/mutant.ps2" \
             > "$OUT/e0/mutant.log" 2>&1; then
          echo "FAIL  a script that dragged BMP1 two units further passed"; fail=1
        elif grep -q "is not the one the script makes" "$OUT/e0/mutant.log"; then
          echo "ok    ⛔ the mutated script (BMP1 dragged by 12, not 10) is rejected"
        else
          tail -3 "$OUT/e0/mutant.log"; echo "FAIL  the e0 mutation failed for the wrong reason"; fail=1
        fi ;;
    e1) echo "--- e1 ⭐ A TABLE BUILT FROM NOTHING (pcs 24), and played twice ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/e1" ui-empty \
          software/pcs/bench/scripts/pcsbuild.ps2 || fail=1 ;;
    e2) echo "--- e2 ⭐ THE MAGNIFIER: fat bits drawn and erased, the box, the layer it left ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/e2" ui-mag \
          software/pcs/bench/scripts/pcsmag.ps2 || fail=1 ;;
    w0) echo "--- w0 ⭐ WORLD: four sliders, the wset they leave, every knob ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/w0" ui-world \
          software/pcs/bench/scripts/pcsworld.ps2 || fail=1 ;;
    c0) echo "--- c0 ⭐ e0's session, gesture after gesture: the mouse queue carried them ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/c0" ui "$OUT/c0.ps2" 4 || fail=1 ;;
    c2) echo "--- c2 ⭐ e2's session, gesture after gesture: the mouse queue carried them ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/c2" ui-mag "$OUT/c2.ps2" 4 || fail=1 ;;
    cX) echo "--- cX ⛔ c0's session with the queue OFF (pcs 25) - this must be REJECTED ---"
        # ⚠ The checker must have RUN and read the recording: a crash or a
        # missing dump is also a nonzero exit, and proves nothing.
        if python3 software/pcs/bench/checkpcs.py "$OUT/cX" ui "$OUT/cX.ps2" \
             > "$OUT/cX/check.log" 2>&1; then
          echo "FAIL  an editor with no mouse queue kept every gesture"; fail=1
        elif grep -q "Traceback" "$OUT/cX/check.log" \
             || ! grep -q "is not the one the script makes" "$OUT/cX/check.log"; then
          tail -5 "$OUT/cX/check.log"; echo "FAIL  the cX check failed for the wrong reason"; fail=1
        else
          grep FAIL "$OUT/cX/check.log" | head -3 | sed 's/^/      /'
          echo "ok    ⛔ with the queue off, a gesture made during a repaint is lost"
        fi ;;
    d0) echo "--- d0 ⭐⭐ SAVE AND LOAD: the session, the table it ended on, the card it left ---"
        PATH="$ROOT/.tools/bin:$PATH" python3 software/pcs/bench/checkpcs.py "$OUT/d0" ui-disk \
          software/pcs/bench/scripts/pcsdisk.ps2 demo2l.pbt \
          "$OUT/sd.img" "$OUT/d0.card/sd.img" || fail=1 ;;
    k0) echo "--- k0 ⭐ THE EDITOR'S KIT PANEL, against EDIT.s's DRAWKIT ---"
        python3 software/pcs/bench/checkpcs.py "$OUT/k0" kit || fail=1 ;;
    m5) echo "--- m5 ⛔ MUTATION: BOUNCE rotates back by TTA - this must FAIL ---"
        mutation m5 "every bounce mirrored" ball || fail=1 ;;
    m2) echo "--- m2 ⛔ MUTATION: the B-polygon paints its records - this must FAIL ---"
        mutation m2 "the backdrop inside out" || fail=1 ;;
  esac
done

echo
[ "$fail" = 0 ] && echo "ok    run-pcs.sh: the span database and the ball are what PPAK.s and RUN.s build, and every mutation was caught"
[ "$fail" = 0 ] || echo "FAIL  run-pcs.sh"
exit "$fail"
