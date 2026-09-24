#!/bin/sh
# ⭐ THE PINBALL TABLE, READ OFF THE CARD, AND WHAT IT COSTS.
#
#   sh software/archive/pinball/run-v3pin.sh          ~25 min.  OUT=dir, FRAMES=n, MODES=...
#
# `pinball` is optimizations.md §10 built: a 640 x 512 table - 327 KB of the
# card's 512 KB ring - with VSCROLL following the ball for one register pair a
# frame written inside the blank, the ball on the hardware sprite, extra balls
# as keyed blits with SAVE-BEHIND, flippers PRE-COMPOSED over their own
# background, and ⭐ the lamps and the six-digit score as PALETTE WRITES.
#
# ⭐ AND SINCE 2026-09-21 THE TABLE IS A FILE.  software/archive/pinball/pcbtable.pic is
# 327,680 bytes - exactly 640 SD blocks - and this bench puts it on the card's
# DATA directory beside the program, which reads it straight into VRAM rows
# 0..511.  ⛔ It cannot be a module: 327,680 bytes is five times the address
# space one may occupy, which is why the table used to be 61 interned 16 x 16
# blocks composed by 1,280 copies.  The art is continuous because the CARD is
# what carries it, and ⭐ ART AND COLLISION ARE NOW SEPARATE FILES: the
# picture is a picture, and the physics reads pcbtable.json's 40 x 32 grid,
# carried in the module by mkpinball.py.
#
# `mvania` asked what a game can put on a screen when the room is in VRAM and
# `monster` what it can when the level is longer than VRAM.  This asks what
# happens when the WHOLE WORLD IS IN VRAM and nothing streams - which is the
# case where the card's scroll is free and its LUT does the work.
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
# ⛔ AND FOUR MUTATIONS, WHICH ARE WHAT MAKE THE GATE WORTH ANYTHING.  m32
# takes each ball's save-behind from one row BELOW where it draws and m64
# never restores blit ball 1; ⭐ m256 LOADS THE PICTURE TO THE WRONG VRAM
# ADDRESS (one row low, so the whole table is rotated through the ring) and
# m512 TRUNCATES THE LOAD at ring row 448.  All four are required to FAIL the
# VRAM compare.  A gate nobody has seen fail is a gate nobody has tested
# (CLAUDE.md), and the last two are the gate on the path this scene gained.
#
# ⚠ WHERE THE PROGRAM AND ITS DATA COME FROM.  Since 2026-09-20 the demos are
# NOT in the ROM disk: they are built and put on an SD card
# (software/nitros9/mksddisk.sh, software/nitros9/bench/run-v3sd.sh), and the 488 K ROM
# image is the rescue system.  This bench therefore boots WITH A CARD in the
# socket, `chx /sd0/cmds` so the shell can fork what is on it, and types
# `pinball`.  ⭐ It used to ask the recipe for its command (CMDS_EXTRA) and
# boot with an empty socket; it cannot any more, because the table is 320 KB
# of data the card is the only thing that can hold.
#
# ⛔ Its exit code is the answer, and `Error #` on the console fails it.
# ⭐ CONTACT SHEETS AND NO VIDEO: a pass is reviewed from the sheets first.
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3pin}
SHEETS=${SHEETS:-$ROOT/software/archive/pinball/pinball-sheets}
FRAMES=${FRAMES:-1050}
BALLS=${BALLS:-3}
MODES=${MODES:-"0 16 1 2 128"}
# ⚠ THE LOAD IS SECONDS OF MACHINE TIME AND IT IS IN EVERY RUN.  rbsd reads
# one 512-byte block a CMD17 and a 6809 shifts every byte through SPI by
# hand, so 320 KB is not free; the budget below is the old 75 plus that.
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-95}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
# ⚠ THE PORT'S TREE IS SHARED AND `make` WIPES `.mods`.  Two builds in one
# recipe directory produce "Cannot open '.mods/x.dr' for output", which reads
# like a broken module and is not one - so NITROS9DIR is honoured HERE too,
# and not only by mkrom.sh, and a private worktree runs the whole bench.
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
export NITROS9DIR
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  python3 software/archive/pinball/mkpinball.py "$NITROS9DIR/level2/arm6309/cmds" > "$OUT/mkart.log" 2>&1 || {
    cat "$OUT/mkart.log"; echo "FAIL  the art did not generate"; exit 1; }
  tail -4 "$OUT/mkart.log"
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD.  A curated DATA of exactly what this scene opens, so the image
# is ~360 KB rather than the ~700 a full demo card now is - and the picture on
# it is compared byte for byte with the source by mksddisk.sh's own round
# trip, which is what says the machine read the art this bench checks against.
PD="$OUT/pindata"
rm -rf "$PD"; mkdir -p "$PD"
cp software/archive/pinball/pcbtable.pic software/archive/pinball/pcbtable.pal "$PD/"
DATA="$PD" sh software/nitros9/mksddisk.sh "$OUT/sd.img" pinball \
  > "$OUT/mksddisk.log" 2>&1 || {
  cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
fail=0
n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=1; fi; }

# run DIR MODE FRAMES BALLS SECONDS
run() {
  D="$OUT/$1"; m=$2; f=$3; nb=$4; secs=$5
  rm -rf "$D"; mkdir -p "$D"
  echo "$m $f $nb" > "$D/args.txt"
  # ⚠ CR, not LF (demo-report.md §15.3).  `chx` moves the EXECUTION directory
  # so the shell can fork what is on the card; `chd` is deliberately NOT done,
  # because it would change the prompt and with it this bench's SERIAL_GATE.
  printf 'chx /sd0/cmds\riniz w5\rpinball %d %d %d >/w5\recho DONE-arm6309\r' \
    "$m" "$f" "$nb" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 VRAMDUMP=vram.bin \
     SDIMG="$OUT/sd.img" \
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
SHEETDIR="$SHEETS" python3 software/archive/pinball/checkv3pin.py $DIRS || fail=1

# ⭐ AND WHERE THE ART CAME FROM, asked of the tools that wrote the card.  The
# gate above compares VRAM with the .pic on this disk; these two say that the
# .pic on the CARD is that same file, and that a full demo card - the one the
# desktop's Applications menu forks this scene from - carries it too.
echo
claim "the picture on the card is byte for byte the one the gate compares against" \
  sh -c "os9 copy -o=0 '$OUT/sd.img,DATA/pcbtable.pic' '$OUT/onthecard.pic' && cmp -s software/archive/pinball/pcbtable.pic '$OUT/onthecard.pic'"
claim "⭐ and mkrom.sh puts it in the demo DATA set, so the DESKTOP can fork this scene" \
  sh -c "cmp -s software/archive/pinball/pcbtable.pic '$OUT/data/pcbtable.pic' && cmp -s software/archive/pinball/pcbtable.pal '$OUT/data/pcbtable.pal'"

# ⛔ THE MUTATION TEST.  Each of these breaks one thing on purpose and the gate
# is REQUIRED to catch it; a run that passed here would mean the gate cannot
# fail, which is worse than not having one.
if [ -z "$NOMUTATE" ]; then
  echo
  echo "⛔ the mutations, which the gate has to catch:"
  MD=""
  for m in 32 64 256 512; do
    run "x$m" "$m" 300 "$BALLS" "$SECONDS_OF_MACHINE"
    MD="$MD $OUT/x$m"
  done
  NOSHEET=1 python3 software/archive/pinball/checkv3pin.py --gate-must-fail $MD || fail=1
fi

# ⚠ /tmp is where the recordings are and they are hundreds of megabytes.  The
# sheets and the logs are what is kept.
[ -n "$KEEPFRAMES" ] || rm -f "$OUT"/*/frames.bin

echo
echo "      $n shell claims, and checkv3pin.py's above"
[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the table ran in every mode; contact sheets in $SHEETS"
