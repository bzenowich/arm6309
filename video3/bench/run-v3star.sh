#!/bin/sh
# ⭐ THE FARM, AND THE DAY CHANGING WITH THE PALETTE AND NOTHING ELSE.
#
#   sh video3/bench/run-v3star.sh        ~25 min.  OUT=dir, FRAMES=n, ACTORS=n
#
# `stardew` (video3/docs/stardew.md, and the port's
# level2/arm6309/cmds/stardew.asm) replaces `overworld`, which belonged to
# the archived video/ card.  A 1024 x 480 farm read off /SD0 straight into
# VRAM, a 640 x 200 view scrolled over it in both axes, the farmer on the
# card's one hardware sprite, chickens and a dog as keyed blits with
# save-behind, crops that grow - and ⭐ THE HEADLINE, which is the one claim
# no other card in this machine could make: the time of day changes by
# PALETTE WRITES AND NOTHING ELSE, six LUT entries a frame inside the blank,
# with not one pixel of the world redrawn.
#
# ⭐ THE RUNS, and each is one leg of the experiment:
#
#   m0    THE SCENE - $FRAMES frames at seven actors, then the settle.
#         The contact sheets and every gate come from this one
#   m1    ⛔ THE CONTROL: the day cycle disabled.  The palette gate's
#         negative - every checkpoint must read the AUTHORED palette and no
#         other, or "the palette changed" is not a claim about anything
#   m2    the same scene with the scroll through SS.Scroll, which is
#         optimizations.md entry 8's comparison measured on a fourth scene
#   m16   the SWEEP, 2, 4 ... 20 actors: where the frame breaks
#
# ⛔ AND THREE MUTATIONS, WHICH ARE WHAT MAKE THE GATES WORTH ANYTHING.
#   x32   ⭐ the tint is applied to the value the card holds instead of to
#         the authored one - stardew.md §2's compounding bug, exactly - and
#         THE COMPOUNDING GATE is required to catch it
#   x64   actor 0 is drawn and never restored: the VRAM gate must catch it
#   x8    the final Wipe is skipped: the VRAM gate must catch that too
#
# ⛔ AND THE NEGATIVE CONTROL: the same ROM and the same keystrokes with an
# EMPTY SOCKET.  The world is a file, so the demo must fail to load and SAY
# SO rather than run on a black farm (stardew.md §5).
#
# ⛔ Its exit code is the answer, and `Error #` on the card run's console
# fails it.  ⭐ CONTACT SHEETS AND NO VIDEO: a pass is reviewed from the
# sheets first (CLAUDE.md, and the demo's own rule).
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3star}
FRAMES=${FRAMES:-1050}
ACTORS=${ACTORS:-7}
MODES=${MODES:-"0 1 2 16"}
MUTS=${MUTS:-"32 64 8"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-95}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  python3 video3/bench/mkstardew.py "$NITROS9DIR/level2/arm6309/cmds" \
    > "$OUT/mkart.log" 2>&1 || {
      cat "$OUT/mkart.log"; echo "FAIL  the art did not generate"; exit 1; }
  tail -6 "$OUT/mkart.log"
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD, MADE BY THE TOOLCHAIN, and its DATA is the world and nothing
# else: 491,520 bytes is most of the image, and mksddisk.sh copies every file
# it is given, so pointing it at mkrom.sh's whole data set would put 800 KB of
# fonts and streams on a card this bench never reads.
FD="$OUT/farmdata"
rm -rf "$FD"; mkdir -p "$FD"
cp video3/bench/stardew.pic "$FD/"
DATA="$FD" sh software/nitros9/mksddisk.sh "$OUT/sd.img" stardew \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the farm card did not build"; exit 1; }
tail -3 "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0

# run DIR MODE FRAMES ACTORS SECONDS IMAGE
run() {
  D="$OUT/$1"; m=$2; f=$3; na=$4; secs=$5; img=$6
  rm -rf "$D"; mkdir -p "$D"
  echo "$m $f $na" > "$D/args.txt"
  # ⚠ CR, not LF (demo-report.md §15.3).  ⛔ And `chx /sd0/cmds` FIRST: the
  # program is on the card and nowhere else.
  printf 'chx /sd0/cmds\riniz w5\rstardew %d %d %d >/w5\recho DONE-arm6309\r' \
    "$m" "$f" "$na" > "$D/typed.txt"
  # ⚠ THE GATE IS "02}", NOT "DD:" - `chx` does not change the prompt but
  # run-v3sd.sh's note applies to any bench that may chd, and `{Term|02}` is
  # in the prompt whatever the data directory is.
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 SDIMG="$img" VRAMDUMP=vram.bin \
     "$OUT/emu" "$ROM" . "$secs" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.txt" || {
    echo "FAIL  $1 did not finish"; tail -5 "$D/emu.txt"; fail=1; }
  case "$1" in
    nocard|nopic) : ;;     # ⛔ an error is what these two are FOR
    *) if grep -n "Error #" "$D/console.txt"; then
         echo "FAIL  $1: a command failed"; fail=1; fi ;;
  esac
  # ⛔ Strip the colour first: `grep '^FAIL'` against a coloured line matches
  # nothing and reads exactly like a pass (CLAUDE.md's seventh trap).
  if grep -q '^FAIL\|^WILD' "$D/emu.txt"; then
    echo "FAIL  $1: the emulator objected"; grep -m4 '^FAIL\|^WILD' "$D/emu.txt"; fail=1; fi
  # ⚠ a recording is ~150 KB a frame: only the runs the palette gate reads
  # keep one, and the sweep never does.
  case "$1" in
    m0|m1|x32) : ;;
    *) [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin" ;;
  esac
}

if [ -z "$NORUN" ]; then
  for m in $MODES; do
    secs=$SECONDS_OF_MACHINE
    f=$FRAMES
    [ "$m" = "16" ] && secs=$((SECONDS_OF_MACHINE + 40))
    run "m$m" "$m" "$f" "$ACTORS" "$secs" "$OUT/sd.img"
  done
fi

DIRS=""
for m in $MODES; do DIRS="$DIRS $OUT/m$m"; done
python3 video3/bench/checkv3star.py $DIRS || fail=1

# ⛔ THE MUTATION TEST.  Each of these breaks one thing on purpose and a gate
# is REQUIRED to catch it; a run that passed here would mean the gates cannot
# fail, which is worse than not having them.
if [ -z "$NOMUTATE" ]; then
  echo
  echo "⛔ the mutations, which the gates have to catch:"
  MD=""
  for m in $MUTS; do
    [ -n "$NORUN" ] || run "x$m" "$m" 450 "$ACTORS" "$SECONDS_OF_MACHINE" "$OUT/sd.img"
    MD="$MD $OUT/x$m"
  done
  NOSHEET=1 python3 video3/bench/checkv3star.py --gate-must-fail $MD || fail=1
fi

# ⛔ THE NEGATIVE CONTROLS: an empty socket, and a card with the PROGRAM and
# no WORLD.  The farm is a 491,520-byte FILE, so the demo must fail to load
# and SAY SO - not paint a black farm and call it night (stardew.md §5).
#
# ⭐ THE SECOND ONE IS THE ONE THAT TESTS THIS PROGRAM.  With no card at all
# the shell cannot even find `stardew`, so nothing of the scene runs; with a
# card that has the command and not stardew.pic, DOpen misses both legs and
# the scene's own error path is what has to answer.
if [ -z "$NONOCARD" ]; then
  echo
  if [ -z "$NORUN" ]; then
    DATA="" sh software/nitros9/mksddisk.sh "$OUT/nopic.img" stardew \
      > "$OUT/mknopic.log" 2>&1 || {
        cat "$OUT/mknopic.log"; echo "FAIL  the world-less card did not build"; exit 1; }
    run nocard 0 120 "$ACTORS" 70 ""
    run nopic  0 120 "$ACTORS" 70 "$OUT/nopic.img"
  fi
  n=0; nf=0
  claim() { n=$((n+1)); what=$1; shift
    if "$@" >/dev/null 2>&1; then echo "ok    $what"
    else echo "FAIL  $what"; nf=$((nf+1)); fi; }
  nc() { grep -q -- "$1" "$OUT/nocard/console.txt"; }
  claim "⛔ with an EMPTY socket the machine still boots to a shell"  nc '/DD:'
  claim "⛔ and /SD0 refuses at §9.0 - E\$NotRdy, not silence"        nc 'Error #246'
  claim "⛔ and the demo is NOT FOUND on the card - the program is not in the ROM" \
    nc 'Error #216'
  claim "⛔ and it FAILS rather than hanging - the run reached the end" \
    grep -q 'SERIAL_STOP seen' "$OUT/nocard/emu.txt"
  claim "⛔ and no crash: nothing printed D.Crash's '!'" \
    sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/nocard/console.txt'"
  np() { grep -q -- "$1" "$OUT/nopic/console.txt"; }
  claim "⛔ with the PROGRAM on the card and no WORLD, stardew says so"  np 'no world file'
  claim "⛔ ...and exits with E\$PNNF rather than painting a black farm"  np 'Error #216'
  claim "⛔ ...and the shell got the machine back"                       np 'DONE-arm6309'
  claim "⛔ ...and the run reached the end rather than hanging" \
    grep -q 'SERIAL_STOP seen' "$OUT/nopic/emu.txt"
  claim "⛔ ...and it drew NO frame of scene: no scroll mark was ever made" \
    sh -c "test -s '$OUT/nopic/marks.txt' && ! grep -q ' M17\$' '$OUT/nopic/marks.txt'"
  echo "      $n claims, $nf failed   (the negative controls)"
  [ "$nf" -eq 0 ] || fail=1
fi

[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the farm ran in every mode; contact sheets beside $OUT/m0"
