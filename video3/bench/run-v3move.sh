#!/bin/sh
# ⭐ MILESTONE 4: THE WINDOW MOVES, AND THE CARD MOVES IT - arm6309
# docs/boot-and-desktop.md §3.5 item 4.
#
#   sh video3/bench/run-v3move.sh        ~7 min.  OUT=dir, NOBUILD=1, NORUN=1
#                                        RUNS='drag' re-does one leg
#
# ⛔ WHAT WAS UNBUILT UNTIL NOW IS THE SHELL USING IT.  `v3drag` has dragged a
# window round a figure-8 with the copy engine since 2026-09-16, and it walks a
# CANNED TABLE OF LEGS that mklegs.py generated - it is a demonstration that
# the engine can do it, on a window that is a recording.  This bench runs
# `desk`'s OWN window: the file manager, listing a real /DD/CMDS, grabbed by
# its tab with a PS/2 packet and dragged by where the pointer actually goes.
#
# What it has to establish, and every one of them off PIXELS:
#
#   1  the manager is up and has walked into /DD/CMDS - NitrOS-9's own 63
#      commands, twelve rows of them, so the thing being dragged is a window
#      with a real listing in it rather than an empty frame
#   2  ⭐ THE WINDOW MOVED, to dozens of distinct positions, and every one of
#      them is inside the travel box desk.asm's own equates define
#   3  ⭐ AND IT WENT WHERE THE MOUSE WENT.  Every position it took is one the
#      PS/2 script put the pointer at, less the grab offset.  ⛔ This is the
#      claim that separates a drag from v3drag: a canned curve would satisfy
#      every other claim here
#   4  ⭐ it came home BIT-EXACT - the frame's CRC after ~165 copy-engine moves
#      is the one it had before the grab.  The CPU never touched a pixel
#   5  ⛔ AND EVERY PIXEL OUTSIDE THE WINDOW IS THE ONE IT WAS BEFORE THE GRAB,
#      desktop icons the window was dragged straight over included.  That is
#      the backing store's whole job (docs/boot-and-desktop.md §3.7)
#   6  ⭐ and the travel really does cross those icons, so the store is being
#      asked a real question rather than a flat blue one
#   7  ⛔ THE NEGATIVE CONTROL: the same session, the same path, and the button
#      is never pressed.  The window must hold exactly ONE position all run.
#      A desktop that dragged on hover, or on a timer, passes 1-6 and fails here
#
# ⚠ THE POINTER IS IN THE PICTURE (video3 composites it as a 16 x 16 sprite),
# so the window is found by its EDGES - a run starting at x and another ending
# at x+FM.W-1 - and never by being solid: the list's folder icons contain
# C.Desk's own blue, so "FM.W not-desktop pixels in a row" is not a window.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3move}
RUNS=${RUNS:-"drag idle"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-150}
# ⛔ A BOUND THE RUN CANNOT REACH, on purpose.  F$Sleep 1 yields rather than
# sleeping a whole tick, so desk's loop runs at ~170 Hz and 9000 passes is
# 53 SECONDS - the drag was being cut off mid-figure-8 by its own iteration
# bound, which desk now reports as DESK-LIM rather than DESK-BYE.
TICKS=${TICKS:-60000}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
DESKASM=${DESKASM:-$NITROS9DIR/level2/arm6309/cmds/desk.asm}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

[ -f "$DESKASM" ] || { echo "FAIL  no $DESKASM (../nitros9 on its arm6309 branch?)"; exit 1; }

if [ -z "$NOBUILD" ]; then
  # ⛔ V3=1 OR NOTHING: desk, the toolbox and SS.Copy are all inside `IFNE V3`.
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
  DATA="$OUT/data" sh software/nitros9/mksddisk.sh "$OUT/sd.img" desk v3paint \
    > "$OUT/mksddisk.log" 2>&1 || { cat "$OUT/mksddisk.log"
    echo "FAIL  the card did not build"; exit 1; }
  cat "$OUT/mksddisk.log"
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
run() {   # run <dir> <CONTROL or "">
  D="$OUT/$1"; rm -rf "$D"; mkdir -p "$D"
  SESSION=1 CONTROL="$2" python3 video3/bench/mkdragps2.py > "$D/drag.ps2"
  # ⚠ CR, not LF.  ⛔ And `chx /sd0/cmds` comes last, so the only things the
  # shell can fork are the card's commands - desk's launcher works in that.
  printf 'iniz w3\rchd /sd0\rchx /sd0/cmds\rdesk /w3 %s\recho DONE-arm6309\r' \
    "$TICKS" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     PS2_SCRIPT="$D/drag.ps2" PS2_SCRIPT_GATE="DESK-READY" \
     "$OUT/emu" "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  CONTROL="$2" python3 video3/bench/checkmove.py "$DESKASM" "$D" \
    > "$D/move.txt" 2> "$D/move.err" || true
  [ -s "$D/move.txt" ] || { cat "$D/move.err"; echo "      0 claims, 1 failed" > "$D/move.txt"; }
  [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
}

if [ -z "$NORUN" ]; then
  for r in $RUNS; do
    case $r in
      drag) run drag "" ;;
      idle) run idle 1 ;;
      *) echo "FAIL  unknown run '$r'"; exit 1 ;;
    esac
  done
fi

N=0; F=0
for r in $RUNS; do
  echo "──────── $r ────────"
  cat "$OUT/$r/move.txt"
  n=$(sed -n 's/.*  \([0-9]*\) claims, \([0-9]*\) failed/\1/p' "$OUT/$r/move.txt")
  f=$(sed -n 's/.*  \([0-9]*\) claims, \([0-9]*\) failed/\2/p' "$OUT/$r/move.txt")
  N=$((N + ${n:-0})); F=$((F + ${f:-1}))
done
echo
echo "      $N claims, $F failed        (logs in $OUT)"
[ "$F" -eq 0 ] || exit 1
