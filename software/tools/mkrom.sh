#!/bin/sh
# Assemble the boot ROM and emit what the simulation loads.
#
#   sh software/tools/mkrom.sh            (from the repository root)
#   npm run rom                           (from hardware/)
#
# Three outputs, in software/boot/:
#   boot.bin   the raw 8 KB image -- what goes in the SST39SF040's first page
#   boot.hex   the same bytes as $readmemh records, for mainboard.v's `rom`
#   boot.lst   A09's listing, which is the only place the encodings are visible
#
# ⚠ THE ADDRESS MAPPING IS THE INTERESTING PART. machine.md 7.2: in boot mode
# and in the vector page the '244 drives physical A20-A13 to zero, so the ROM
# byte a logical address reaches is `LA & $1FFF` -- and after RUN the block-7
# entry points at the same physical page, so it is the same byte. The source
# therefore ORGs at $E000 and the image is offset 0: logical $E000 IS ROM $0000
# and logical $FFFE IS ROM $1FFE, which is the byte the reset vector comes from.
set -e

cd "$(dirname "$0")/../.."          # the repository root
ROOT=$(pwd)
OUT="$ROOT/software/boot"
A09_DIR="${A09_DIR:-/tmp/arm6309-a09}"

sh "$ROOT/software/tools/fetch-a09.sh" >/dev/null
A09="$A09_DIR/a09"

"$A09" -B"$OUT/boot.bin" -L"$OUT/boot.lst" "$OUT/boot.asm"

size=$(wc -c < "$OUT/boot.bin")
if [ "$size" -ne 8192 ]; then
  echo "FAIL  boot.bin is $size bytes, want 8192 - the image must be ROM page 0 exactly"
  exit 1
fi

# $readmemh, one byte per line from address 0. mainboard.v's rom[] is 1 MB and
# fills from the bottom, which is where page 0 is.
od -An -v -tx1 -w16 "$OUT/boot.bin" | tr -s ' ' '\n' | grep -v '^$' > "$OUT/boot.hex"

lines=$(wc -l < "$OUT/boot.hex")
[ "$lines" -eq 8192 ] || { echo "FAIL  boot.hex has $lines records, want 8192"; exit 1; }

# The reset vector, read back out of the image the machine will actually run,
# because "it assembled" and "it will fetch" are different claims.
vec=$(od -An -v -tx1 -j 8190 -N 2 "$OUT/boot.bin" | tr -d ' ')
echo "ok    boot.bin 8192 bytes, reset vector at ROM \$1FFE = \$$vec"
