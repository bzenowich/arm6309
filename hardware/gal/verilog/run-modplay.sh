#!/bin/sh
# Play a module on the REAL CARD and render what its converters were given.
#
#   sh gal/verilog/run-modplay.sh song.mod [seconds]      (from hardware/)
#   npm run check:modplay                                 (the built-in probe)
#
# ⭐ WHAT IS UNDER TEST: audio_card.v - U1 (audio.v) and U2 (aseq.v), generated
# by emit.ts from the same Cell term lists jedec/cupl.ts compiles for
# fit1508.exe - plus the board between them. Nothing else. The sample bytes and
# the register stream go in through the host port at $FF40-$FF4F over 6809 bus
# cycles; the four AD7528 pairs' codes come out; audio/tools/dacwav renders
# those through render.c's analogue chain, which is resistors and an op-amp and
# has no RTL to have.
#
# ⛔ WHAT IS NOT: audio/refplayer/card.c, the host-side model of this card. It
# is not in this pipeline at any point. refplayer supplies two things and they
# are both SOFTWARE outputs - modplayer.md §4's loader (where the samples land
# in card RAM) and §5's tick engine (which register gets which byte on which
# tick) - and the second is the trace the 6309 port is contracted to reproduce
# byte for byte.
#
# ⭐ AND THE CONTROL IS WHAT MAKES IT READABLE. Three renders come out:
#
#   card.wav   the RTL card, driven by that trace
#   ref.wav    refplayer, driven by its own replayer - the CONTROL
#   (libopenmpt, inside abcompare.py)               - the REFERENCE
#
# libopenmpt carries Antti Lankila's Paula emulation and is the independent
# implementation. Scoring the card against it means nothing on its own, because
# a band-limited resampler and a zero-order hold must differ. Scoring the card
# against it AND refplayer against it, and comparing the two scores, is the
# experiment: refplayer's number is what this project's understanding of the
# module is worth, and a card that scores like it is a card that plays what the
# software asked for. A card that scores WORSE is hardware.
set -e
cd "$(dirname "$0")"
HERE=$(pwd)
ROOT=$(cd ../../.. && pwd)

MOD=${1:?usage: run-modplay.sh song.mod [seconds]}
SECS=${2:-4}
OUT=${OUT:-/tmp/arm6309-modplay}
mkdir -p "$OUT"
name=$(basename "$MOD" .mod)

REF="$ROOT/build-host/refplayer"
DACWAV="$ROOT/build-host/dacwav"
[ -x "$REF" ] || { echo "build-host/refplayer missing - cmake --build build-host" >&2; exit 1; }
[ -x "$DACWAV" ] || { echo "build-host/dacwav missing - cmake --build build-host" >&2; exit 1; }

echo "-- 1. the software: the loader's sample image and the replayer's trace"
"$REF" --wav "$OUT/$name.ref.wav" --trace "$OUT/$name.trace" \
       --sram "$OUT/$name.sram" --seconds "$SECS" "$MOD"

echo
echo "-- 2. the card: audio_card.v, driven through its host port"
V="verilator --binary --timing -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL"
V="$V -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-BLKSEQ"
$V --top-module modplay_tb audio_card.v audio.v aseq.v modplay_tb.sv \
   -o modplay_tb > /dev/null

# 3546895 colour clocks per second - the card's own rate (audio.md §4.1).
CC=$(awk "BEGIN{printf \"%d\", $SECS * 3546895}")
out=$(mktemp)
trap 'rm -f "$out"' EXIT
./obj_dir/modplay_tb +sram="$OUT/$name.sram" +trace="$OUT/$name.trace" \
                     +dac="$OUT/$name.dac" +cc="$CC" | tee "$out"

echo
echo "-- 3. the analogue chain, and the file"
"$DACWAV" "$OUT/$name.card.wav" "$OUT/$name.dac"

echo
echo "-- 4. the A/B, both against libopenmpt"
python3 "$ROOT/audio/tools/modcompare/abcompare.py" "$MOD" --seconds "$SECS" \
        --wav "$OUT/$name.card.wav" --label "card RTL" || true
echo
python3 "$ROOT/audio/tools/modcompare/abcompare.py" "$MOD" --seconds "$SECS" \
        --wav "$OUT/$name.ref.wav" --label "refplayer (control)" || true

ok=$(grep -c '^ok' "$out" || true)
bad=$(grep -c '^FAIL' "$out" || true)
echo
echo "$ok claims, $bad failed        (renders in $OUT)"
[ "$bad" -eq 0 ]
