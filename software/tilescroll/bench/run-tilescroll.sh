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
# ⭐⭐ AND THE ACTORS ARE THE SPRITE WALKER'S (hardware/video3/docs/plan.md
# §6.4, scrolling.md §9): one GO in the blank restores, saves and draws every
# one of them, every frame.  The emulator writes walk.txt - a line a frame:
# where the walk started and ended, how many displayed lines it was still
# writing when the beam got to them (a TEAR), and the topmost line a keyed
# draw landed on.  Two legs are measured:
#   m0    the default cast, six creatures and the hero (1.18 ms of walk in a
#         1.43 ms blank): EVERY walk ends in the blank and NOTHING tears -
#         with the flyers in the top 64 rows, which is what makes "nothing
#         tears" mean something rather than "nothing was up there"
#   s1    ⛔ THIRTEEN creatures, ~2.4 ms of walk: it is REQUIRED to tear, and
#         the tears are REQUIRED to be in the top rows only - the walk runs
#         ~30 lines into the picture and no further.  Its ring must still be
#         exact: a late copy is a tear on screen, never a wrong byte in VRAM.
#
# ⛔ Its exit code is the answer.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/scroll}
FRAMES=${FRAMES:-1200}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-140}
RUNS=${RUNS:-"m0 m1 m2 s1"}
STRESS=${STRESS:-13}
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
# ⛔ AND A STARTUP OF ITS OWN.  The system's runs `vconsole &` and `desk`, and
# desk never prints the shell prompt the typing is gated on.  (The E$WADef, 184,
# that the scene's DWSet once answered here was `iniz` leaving /w5 defined -
# `Screen` now ends the window first, as pcs does.)
printf 'chx /dd/cmds\r' > "$OUT/bench_startup"
STARTUP="$OUT/bench_startup" DATA="$SD" sh software/nitros9/mksyscard.sh "$OUT/sd.img" tilescroll \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
tail -3 "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   hardware/cpu/sim/cpu6809.c hardware/cpu/sim/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0

# run NAME MODE [CREATURES]
run() {
  D="$OUT/$1"; m=$2; n=${3:-0}
  rm -rf "$D"; mkdir -p "$D"
  # ⚠ CR, NOT LF.  The shell's line terminator is carriage return; a script
  # written with newlines is typed in full, echoed in full, and executed not
  # at all - and what it looks like is a program that ran and printed nothing
  # (demo-report.md §15.3, and it cost a run here on 2026-09-23).
  printf 'chx /sd0/cmds\riniz w5\rtilescroll %d %d %d >/w5\recho DONE-arm6309\r' \
    "$m" "$FRAMES" "$n" > "$D/typed.txt"
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
    s1) run s1 0 "$STRESS" ;;
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
    s1) echo "--- s1: $STRESS creatures - the ring must STILL be exact ---"
        python3 software/tilescroll/bench/checktilescroll.py "$OUT/s1" "$FRAMES" || fail=1 ;;
  esac
done

# walk NAME - the walker's frames, summarised from walk.txt:
#   frames  walks  pending  late(ended past the blank)  torn-lines  torn-frames
#   torn-top  torn-bottom  top64(frames with a keyed draw on lines 0-63)  draw-top
walk() {
  [ -f "$OUT/$1/walk.txt" ] || { echo "FAIL  $1: no walk.txt"; fail=1; echo "0 0 0 0 0 0 -1 -1 0 -1"; return; }
  # ⚠ THE LAST LINE IS NOT A SCENE FRAME: it holds the Wipe, a restore-only
  # walk issued after the scene stopped and wherever the beam happens to be.
  # It is counted as a walk and judged by the ring gate, not here.
  sed '$d' "$OUT/$1/walk.txt" > "$OUT/$1/walk.txt.scene"
  awk '{ f++; w += $4; if ($8 == -1) p++; else if ($8 < $6) l++
         t += $10; if ($10 > 0) { tf++; if (tt == "" || $12 < tt) tt = $12; if ($14 > tb) tb = $14 }
         if ($16 >= 0 && $16 < 64) t64++; if ($16 >= 0 && (dt == "" || $16 < dt)) dt = $16 }
       END { printf "%d %d %d %d %d %d %d %d %d %d\n", f, w + wl, p+0, l+0, t+0, tf+0,
             tt == "" ? -1 : tt, tb == "" ? -1 : tb+0, t64+0, dt == "" ? -1 : dt }' \
    wl="$(tail -1 "$OUT/$1/walk.txt" | awk '{print $4}')" "$OUT/$1/walk.txt.scene"
}
claim() {  # claim TEXT CONDITION...
  t=$1; shift
  if "$@"; then echo "ok    $t"; else echo "FAIL  $t"; fail=1; fi
}
for r in $RUNS; do
  case "$r" in
    m0) echo; echo "=== m0: the default cast, walked ==="
        set -- $(walk m0)
        echo "      $1 frames, $2 walks; $5 torn lines; keyed draws on lines 0-63 in $9 frames, topmost line ${10}"
        claim "a walk every frame of the scene ($2 >= $FRAMES)" [ "$2" -ge "$FRAMES" ]
        claim "every walk finished ($3 pending)" [ "$3" -eq 0 ]
        claim "every walk ended in the blank it started in ($4 late)" [ "$4" -eq 0 ]
        claim "⭐ NOTHING TORE: $5 lines over $1 frames" [ "$5" -eq 0 ]
        claim "... and the actors were up there: keyed draws in the top 64 lines in $9 frames (>= $((FRAMES / 10)))" [ "$9" -ge $((FRAMES / 10)) ]
        claim "... as high as line ${10} (< 8)" [ "${10}" -ge 0 -a "${10}" -lt 8 ]
        grep -q '0 contract violations' "$OUT/m0/emu.txt"; claim "the walk contract held (WMODE, WADV, no copy under a GO)" [ $? -eq 0 ] ;;
    s1) echo; echo "=== s1 ⛔ $STRESS creatures: this MUST tear, and only at the top ==="
        set -- $(walk s1)
        echo "      $1 frames, $2 walks; $5 torn lines in $6 frames, lines $7..$8; walks ending past the blank: $4"
        claim "a walk every frame of the scene ($2 >= $FRAMES)" [ "$2" -ge "$FRAMES" ]
        claim "every walk finished ($3 pending)" [ "$3" -eq 0 ]
        claim "⛔ the overlong walk DID tear ($5 lines in $6 frames)" [ "$5" -gt 0 ]
        claim "... and only in the top rows: the lowest torn line is $8 (< 64)" [ "$8" -ge 0 -a "$8" -lt 64 ]
        grep -q '0 contract violations' "$OUT/s1/emu.txt"; claim "the walk contract held" [ $? -eq 0 ] ;;
  esac
done

echo
[ "$fail" = 0 ] && echo "ok    run-tilescroll.sh: the engine is byte-exact, both mutations were caught, and the walker tears only when it is made to"
[ "$fail" = 0 ] || echo "FAIL  run-tilescroll.sh"
exit "$fail"
