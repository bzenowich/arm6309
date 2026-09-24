#!/bin/sh
# video3's character mode on the host emulator, judged pixel for pixel.
#
#   sh hardware/video3/bench/run-v3sprite.sh [seconds]        OUT=dir overrides
#
# The emulator carries BOTH card models and VIDEO3=1 selects video3's; the
# existing suite (run-emu.sh, run-vid.sh, run-emu for NitrOS-9) drives video/'s
# and is unaffected.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
SECS=${1:-10}
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/v3sprite}
mkdir -p "$B" "$OUT"
sh software/tools/fetch-a09.sh > /dev/null
A09="${A09_DIR:-$(cd "$_here/../../.." && pwd)/.tools/a09}/a09"
python3 hardware/video3/bench/mkv3sprite.py hardware/video3/bench/v3sprite.asm hardware/video3/bench/v3sprite.json > /dev/null
"$A09" -B$B/v3sprite.bin -L$B/v3sprite.lst hardware/video3/bench/v3sprite.asm > $B/v3sprite.log 2>&1 || { cat $B/v3sprite.log; exit 1; }
grep -qi error $B/v3sprite.log && { cat $B/v3sprite.log; exit 1; }
python3 - "$ROOT" "$B" <<'PY'
import sys
root, b = sys.argv[1], sys.argv[2]
rom = bytearray(b"\xFF" * (1 << 20))
rom[0:8192] = open(root + "/software/boot/boot.bin", "rb").read()
code = open(b + "/v3sprite.bin", "rb").read()
rom[8192:8192 + len(code)] = code
open(b + "/v3sprite.rom", "wb").write(rom)
PY
cc -O2 -w -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"
VIDEO3=1 "$OUT/emu" $B/v3sprite.rom "$OUT" "$SECS" > "$OUT/emu.out" 2> "$OUT/emu.log" || true
# ⚠ the ROM reports $E0-$EF for a fault of its own - an arm that did not
# take, say - and the emulator stops there.  Say so rather than letting it
# surface as a missing frame.
grep -q "the ROM reported" "$OUT/emu.log" && { grep "the ROM reported" "$OUT/emu.log"; exit 1; }
grep -q "progress \$A0" "$OUT/emu.log" || { echo "FAIL  the ROM never reached \$A0"; tail -5 "$OUT/emu.log"; exit 1; }
python3 hardware/video3/tools/v3model.py "$OUT/frames.bin" hardware/video3/bench/v3sprite.json
