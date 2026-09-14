#!/bin/sh
# Build the NitrOS-9 ROM: software/boot/boot.bin as page 0, and the port's
# recipe in $NITROS9DIR (branch arm6309) for the rest. Writes, into $1 (default
# /tmp/arm6309-nitros9):
#
#   arm6309_rom.bin   the 1 MB image
#   arm6309_rom.hex   the same bytes as $readmemh records, for mainboard.v's rom[]
#
# Used by software/nitros9/run-emu.sh and by hardware/gal/verilog/run-machine.sh
# for +scenario=nitros9.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${1:-/tmp/arm6309-nitros9}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
export PATH="$ROOT/.tools/bin:$PATH"
mkdir -p "$OUT"

[ -n "$NITROS9DIR" ] && [ -d "$NITROS9DIR/recipes/arm6309" ] || {
  echo "FAIL  no NitrOS-9 tree with recipes/arm6309 (set NITROS9DIR; branch arm6309)"; exit 1; }
command -v lwasm >/dev/null && command -v os9 >/dev/null || {
  echo "FAIL  no lwasm/os9: run sh software/tools/fetch-nitros9-tools.sh"; exit 1; }

sh software/tools/mkrom.sh > "$OUT/mkrom.log" 2>&1 || { tail -5 "$OUT/mkrom.log"; exit 1; }
make -C "$NITROS9DIR/recipes/arm6309/l2" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" \
  > "$OUT/build.log" 2>&1 || { grep -v '^lwasm\|^lwlink' "$OUT/build.log" | tail -20; echo "FAIL  the ROM did not build"; exit 1; }

cp "$NITROS9DIR/recipes/arm6309/l2/arm6309_rom.bin" "$OUT/arm6309_rom.bin"
[ "$(wc -c < "$OUT/arm6309_rom.bin")" -eq 1048576 ] || { echo "FAIL  the ROM is not 1 MB"; exit 1; }
od -An -v -tx1 -w16 "$OUT/arm6309_rom.bin" | tr -s ' ' '\n' | grep -v '^$' > "$OUT/arm6309_rom.hex"
[ "$(wc -l < "$OUT/arm6309_rom.hex")" -eq 1048576 ] || { echo "FAIL  the hex is not 1 MB of records"; exit 1; }
# page 0 must be this repository's boot ROM, byte for byte
cmp -s -n 8192 "$OUT/arm6309_rom.bin" software/boot/boot.bin || { echo "FAIL  ROM page 0 is not software/boot/boot.bin"; exit 1; }
echo "ok    $OUT/arm6309_rom.bin and .hex, page 0 = software/boot/boot.bin"
