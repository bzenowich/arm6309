#!/bin/sh
# The storage card in software/emu/machine.c, driven through its four
# registers as hardware/storage/docs/sdcard.md §9 says a driver must.
#
#   sh software/emu/test/run-sdtest.sh
#   OUT=dir sh software/emu/test/run-sdtest.sh     (default: obj_sd/ here)
#
# ⛔ THE EXIT CODE IS THE ANSWER. sdtest.c prints one line per claim and ends
# with "N claims, M failed"; a non-zero M is a non-zero exit.
#
# It includes machine.c itself (with `main` renamed), so there is exactly one
# C model of this card in the repository and the test cannot pass against a
# copy of itself. ~2 s, and it needs nothing but a C compiler.
set -e
cd "$(dirname "$0")"
ROOT=$(cd ../../.. && pwd)
OUT=${OUT:-obj_sd}
mkdir -p "$OUT"
cc -O2 -w -I"$ROOT/hardware/audio/refplayer" -o "$OUT/sdtest" sdtest.c ../cpu6809.c ../hd6309.c "$ROOT/hardware/audio/refplayer/card.c"
"$OUT/sdtest" "$OUT"
