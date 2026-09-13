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

# The A/B needs numpy and libopenmpt. Checked HERE, before two minutes of
# simulation, and fatal: an A/B that cannot run is a check that did not run.
python3 -c "import numpy, sys; sys.path.insert(0, '$ROOT/audio/tools/modcompare'); import omptrender; omptrender._lib()" \
  || { echo "FAIL  the A/B cannot run: python3 needs numpy and libopenmpt.so.0" >&2; exit 1; }

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
# The bench's output is KEPT beside the renders. It used to go to a mktemp file
# removed on EXIT, so a failing run deleted the FAIL lines it had just counted.
out="$OUT/$name.log"
./obj_dir/modplay_tb +sram="$OUT/$name.sram" +trace="$OUT/$name.trace" \
                     +dac="$OUT/$name.dac" +cc="$CC" | tee "$out"

echo
echo "-- 3. the analogue chain, and the file"
"$DACWAV" "$OUT/$name.card.wav" "$OUT/$name.dac"

echo
echo "-- 4. the A/B, both against libopenmpt, and the card gated against the control"
# ⭐ ONE INVOCATION, AND ITS EXIT CODE COUNTS. Both scorings used to run under
# `|| true`, so no acoustic result could fail this check - the 12 dB volume
# error and 2026-09-12's frozen channels both printed and passed. --control
# applies this file's own rule: a card that scores worse than refplayer is
# hardware. abcompare.py records the margins.
#
# ⚠ The verdict is read from the LOG, not from the pipeline: sh has no pipefail,
# so `python3 ... | tee` returns tee's status. A crash prints no verdict line
# and fails too.
python3 "$ROOT/audio/tools/modcompare/abcompare.py" "$MOD" --seconds "$SECS" \
        --wav "$OUT/$name.card.wav" --label "card RTL" \
        --control "$OUT/$name.ref.wav" 2>&1 | tee -a "$out" || true
acoustic=0
grep -q '^ok    the card scores no worse than the control' "$out" || acoustic=1
[ "$acoustic" -eq 0 ] || grep -q '^FAIL' "$out" \
  || echo "FAIL  the A/B produced no verdict" | tee -a "$out"

ok=$(grep -c '^ok' "$out" || true)
bad=$(grep -c '^FAIL' "$out" || true)
echo
echo "$ok claims, $bad failed        (renders and $name.log in $OUT)"
[ "$bad" -eq 0 ] && [ "$acoustic" -eq 0 ]
