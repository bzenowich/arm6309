#!/bin/sh
# video3's character mode on the host emulator, judged pixel for pixel.
#
#   sh video3/bench/run-v3char.sh [seconds]        OUT=dir overrides
#
# The emulator carries BOTH card models and VIDEO3=1 selects video3's; the
# existing suite (run-emu.sh, run-vid.sh, run-emu for NitrOS-9) drives video/'s
# and is unaffected.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
SECS=${1:-8}
OUT=${OUT:-/tmp/arm6309-v3char}
B=software/demo/build
mkdir -p "$B" "$OUT"
sh software/tools/fetch-a09.sh > /dev/null
A09="${A09_DIR:-/tmp/arm6309-a09}/a09"
python3 video3/bench/mkv3char.py video3/bench/v3char.asm video3/bench/v3char.json > /dev/null
"$A09" -B$B/v3char.bin -L$B/v3char.lst video3/bench/v3char.asm > $B/v3char.log 2>&1 || { cat $B/v3char.log; exit 1; }
grep -qi error $B/v3char.log && { cat $B/v3char.log; exit 1; }
python3 - "$ROOT" "$B" <<'PY'
import sys
root, b = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xFF" * (1 << 20))
rom[0:8192] = open(root + "/software/boot/boot.bin", "rb").read()
code = open(b + "/v3char.bin", "rb").read()
rom[8192:8192 + len(code)] = code
open(b + "/v3char.rom", "wb").write(rom)
PY
cc -O2 -w -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"
VIDEO3=1 "$OUT/emu" $B/v3char.rom "$OUT" "$SECS" > "$OUT/emu.out" 2> "$OUT/emu.log" || true
# ⚠ the ROM reports $E0-$EF for a fault of its own - an arm that did not
# take, say - and the emulator stops there.  Say so rather than letting it
# surface as a missing frame.
grep -q "the ROM reported" "$OUT/emu.log" && { grep "the ROM reported" "$OUT/emu.log"; exit 1; }
grep -q "progress \$A0" "$OUT/emu.log" || { echo "FAIL  the ROM never reached \$A0"; tail -5 "$OUT/emu.log"; exit 1; }
python3 video3/tools/v3model.py "$OUT/frames.bin" video3/bench/v3char.json
