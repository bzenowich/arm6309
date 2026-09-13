#!/bin/sh
# The demo on the whole machine - demo_tb.sv - and the video file it makes.
#
#   sh gal/verilog/run-demo.sh [seconds]          (from hardware/)
#   OUT=/some/dir sh gal/verilog/run-demo.sh 30
#
# Budget for it: about two minutes of wall clock per second of machine.
set -e
cd "$(dirname "$0")"
ROOT=$(cd ../../.. && pwd)
SECS=${1:-30}
OUT=${OUT:-/tmp/arm6309-demo}
mkdir -p "$OUT"

# POST_ONLY=1 skips the build and the simulation and re-runs the checks and the
# encode on what is already in $OUT.
if [ -z "$POST_ONLY" ]; then
sh "$ROOT/software/demo/build.sh"
# the generated parts, from the term lists - run.sh does not, and a stale one is
# a previous design (CLAUDE.md)
(cd ../.. && ./node_modules/.bin/bun run gal/verilog/gen.ts > /dev/null)

WAIVE="-Wno-SIDEEFFECT -Wno-UNOPTFLAT -Wno-CASEX -Wno-GENUNNAMED -Wno-PINMISSING"
WAIVE="$WAIVE -Wno-UNUSEDPARAM -Wno-VARHIDDEN -Wno-TIMESCALEMOD -Wno-CASEINCOMPLETE"
WAIVE="$WAIVE -Wno-BLKSEQ -Wno-SYNCASYNCNET -Wno-MULTIDRIVEN -Wno-LATCH"
WAIVE="$WAIVE -Wno-UNSIGNED -Wno-CMPCONST -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDSIGNAL"
V="verilator --binary --timing -Wall -Wno-DECLFILENAME $WAIVE --timescale 1ns/1ps -O3"

SRC="machine.v mainboard.v ../clkdec.v ../mmu.v u9.v u10.v"
SRC="$SRC video_card.v vctrl.v vaddr.v vsup.v audio_card.v audio.v aseq.v"
SRC="$SRC ../../vendor/mc6809/mc6809e.v ../../vendor/mc6809/mc6809i.v"
$V --top-module demo_tb -Mdir obj_demo $SRC demo_tb.sv -o demo_tb > "$OUT/build.log" 2>&1 \
  || { tail -30 "$OUT/build.log"; exit 1; }

./obj_demo/demo_tb +out="$OUT" +secs="$SECS" +rom="$ROOT/software/demo/build/rom.hex" | tee "$OUT/demo.log"
fi
fail=0
grep -q '^demo_tb OK' "$OUT/demo.log" || fail=1

echo
echo "-- the register stream at the backplane, against audio/refplayer"
# ⭐ THE WHOLE RUN, not a window: every write the 6809 made to the real card,
# over the real bus, numbered by tick, against mod_replay.c's own trace. The
# last tick is dropped from both, because the run can end inside it.
SECS=$(awk '/^end_ps/ {printf "%d", $2 / 1e12}' "$OUT/sync.txt")
"$ROOT/build-host/refplayer" --trace "$OUT/ref.trace" --seconds $((SECS + 2)) \
    "$ROOT/software/demo/build/demo.mod" > /dev/null
T=$(tail -1 "$OUT/card.trace" | awk '{print $1 - 1}')
awk -v t="$T" '$1+0 <= t' "$OUT/card.trace" > "$OUT/card.cmp"
awk -v t="$T" '$1+0 <= t' "$OUT/ref.trace" > "$OUT/ref.cmp"
if [ "$T" -gt 0 ] && cmp -s "$OUT/card.cmp" "$OUT/ref.cmp"; then
  echo "ok    ⭐ the card was sent refplayer's register stream, byte for byte: $(wc -l < "$OUT/ref.cmp") writes over $T ticks"
else
  echo "FAIL  the card's register stream differs from refplayer's (through tick $T):"
  diff "$OUT/ref.cmp" "$OUT/card.cmp" | head -8
  fail=1
fi

echo
echo "-- the sound: the RTL card against card.c given the SAME writes at the SAME instants"
# tracewav.c says why this is the control and refplayer is not: in this run the
# 6809 makes the writes, milliseconds after each tick, and refplayer makes them
# at once. Fed card.times, card.c and render.c render what the card should have
# produced from what it was actually sent, on dacwav's own time base - so the
# two files line up sample for sample and abcompare's gate applies as written.
cc -O2 -w -I"$ROOT/audio/refplayer" -o "$OUT/tracewav" "$ROOT/software/demo/tools/tracewav.c" \
   "$ROOT/audio/refplayer/card.c" "$ROOT/audio/refplayer/mod_load.c" \
   "$ROOT/audio/refplayer/render.c" -lm
"$ROOT/build-host/dacwav" "$OUT/card.wav" "$OUT/card.dac" > /dev/null
"$OUT/tracewav" "$OUT/model.wav" "$ROOT/software/demo/build/demo.mod" "$OUT/card.times"
python3 - "$OUT" <<'PY'
import sys, wave
out = sys.argv[1]
sync = dict(l.split() for l in open(out + "/sync.txt"))
start = (int(sync["music_ps"]) - int(sync["cc0_ps"])) / 1e12
end = (int(sync["end_ps"]) - int(sync["cc0_ps"])) / 1e12 - 0.5
for name in ("card", "model"):
    w = wave.open(f"{out}/{name}.wav"); r = w.getframerate()
    w.setpos(int(start * r)); data = w.readframes(int((end - start) * r))
    o = wave.open(f"{out}/{name}.music.wav", "wb"); o.setnchannels(w.getnchannels())
    o.setsampwidth(w.getsampwidth()); o.setframerate(r); o.writeframes(data); o.close()
print(f"      the module starts {start:.3f} s into the card's time base; {end - start:.1f} s compared")
open(out + "/music_len.txt", "w").write(f"{end - start:.2f}\n")
PY
LEN=$(cat "$OUT/music_len.txt")
python3 "$ROOT/audio/tools/modcompare/abcompare.py" "$ROOT/software/demo/build/demo.mod" --seconds "$LEN" \
    --wav "$OUT/card.music.wav" --label "card RTL, demo run" --control "$OUT/model.music.wav" 2>&1 | tee "$OUT/ab.log" || true
grep -q '^ok    the card scores no worse than the control' "$OUT/ab.log" || fail=1
# and the null test the shared time base makes possible - REPORTED, NOT GATED.
# The RTL takes a write a few colour clocks after its strobe (audio.md 9.4.4) and
# starts a channel's period count on its own slot, so at the top of the band the
# two differ in phase by design; abcompare's gate above is the criterion.
python3 - "$OUT" <<'PY'
import sys, wave
import numpy as np
out = sys.argv[1]
def rd(n):
    w = wave.open(f"{out}/{n}.music.wav"); a = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
    return a.reshape(-1, 2)
a, b = rd("card"), rd("model")
n = min(len(a), len(b)); a, b = a[:n], b[:n]
for ch, name in ((0, "left"), (1, "right")):
    sig = np.sqrt((b[:, ch] ** 2).mean()); res = np.sqrt(((a[:, ch] - b[:, ch]) ** 2).mean())
    c = np.corrcoef(a[:, ch], b[:, ch])[0, 1]
    print(f"      {name}: sample for sample, the RTL card and card.c on the same writes correlate {c:.4f}, residual {20*np.log10(res/sig) if res > 0 else -999:.1f} dB")
PY

echo
echo "-- the picture, against the source and the model"
python3 "$ROOT/software/demo/tools/checkdemo.py" "$OUT" "$ROOT/software/demo/build" || fail=1

echo
echo "-- the file"
python3 "$ROOT/software/demo/tools/mkvideo.py" "$OUT" "$OUT/demo.mp4" || fail=1
exit $fail
