#!/bin/sh
# Build the demo ROM: assets, layout, assemble, image.
#
#   sh software/demo/build.sh            (from anywhere)
#
# Everything lands in software/demo/build/, which is not tracked: every file
# in it is regenerated from the sources here, software/boot/boot.bin and
# audio/refplayer/period_table.c.
set -e
cd "$(dirname "$0")"
ROOT=$(cd ../.. && pwd)
B=build
mkdir -p $B

sh "$ROOT/software/tools/mkrom.sh" > /dev/null
sh "$ROOT/software/tools/fetch-a09.sh" > /dev/null
A09="${A09_DIR:-/tmp/arm6309-a09}/a09"

# MOD=path.mod builds the ROM around another module (it is copied to demo.mod)
if [ -n "$MOD" ]; then cp "$MOD" $B/demo.mod; fi
[ -f $B/demo.mod ]    || python3 tools/mkmod.py $B/demo.mod
[ -f $B/parrots-image.jpg ] || [ -f $B/parrots.png ] || python3 tools/mkparrots.py $B/parrots.raw $B/parrots.png
python3 tools/mkgame.py $B
python3 tools/mkshow.py $B
python3 tools/mkdemorom.py layout $B

DEFS=""
[ -n "$QUICK" ] && DEFS="-DQUICK=1"
"$A09" $DEFS -B$B/demo.bin -L$B/demo.lst demo.asm > $B/a09.log 2>&1 || { cat $B/a09.log; exit 1; }
if grep -qi "error" $B/a09.log; then cat $B/a09.log; exit 1; fi
# ... and the replayer alone, for the benches with no video card
"$A09" -DREPLAY=1 -B$B/replay.bin -L$B/replay.lst demo.asm > $B/a09-replay.log 2>&1 || { cat $B/a09-replay.log; exit 1; }
if grep -qi "error" $B/a09-replay.log; then cat $B/a09-replay.log; exit 1; fi

python3 tools/mkdemorom.py image $B
python3 tools/mkdemorom.py image $B replay.bin rom-replay
