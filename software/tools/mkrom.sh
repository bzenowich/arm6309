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
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e

cd "$(dirname "$0")/../.."          # the repository root
ROOT=$(pwd)
OUT="$ROOT/software/boot"
# the image is a tracked design output; its hex and listing are build output
B="$OUT/build"
mkdir -p "$B"
A09_DIR="${A09_DIR:-$(cd "$_here/../.." && pwd)/.tools/a09}"

sh "$ROOT/software/tools/fetch-a09.sh" >/dev/null
A09="$A09_DIR/a09"

"$A09" -B"$OUT/boot.bin" -L"$B/boot.lst" "$OUT/boot.asm"

size=$(wc -c < "$OUT/boot.bin")
if [ "$size" -ne 8192 ]; then
  echo "FAIL  boot.bin is $size bytes, want 8192 - the image must be ROM page 0 exactly"
  exit 1
fi

# $readmemh, one byte per line from address 0. mainboard.v's rom[] is 1 MB and
# fills from the bottom, which is where page 0 is.
od -An -v -tx1 -w16 "$OUT/boot.bin" | tr -s ' ' '\n' | grep -v '^$' > "$B/boot.hex"

lines=$(wc -l < "$B/boot.hex")
[ "$lines" -eq 8192 ] || { echo "FAIL  boot.hex has $lines records, want 8192"; exit 1; }

# ⛔ THE VECTORS ARE COMPARED, NOT PRINTED. This used to print the reset vector
# behind an `ok` prefix without comparing it to anything, so a mis-assembled
# vector read as a claim. Each of the seven is now checked three ways: the two
# bytes in boot.bin at ROM $1FF2-$1FFF, the value A09's listing says that FDB
# assembled to, and the address of the label it names - so "it assembled",
# "the image holds it" and "it points where the source says" are one claim.
fail=0
for v in FFF2:SWI3 FFF4:SWI2 FFF6:FIRQ FFF8:IRQ FFFA:SWI FFFC:NMI FFFE:RESET; do
  addr=${v%%:*}; name=${v#*:}
  off=$(( 0x$addr - 0xE000 ))
  img=$(od -An -v -tx1 -j "$off" -N 2 "$OUT/boot.bin" | tr -d ' \n' | tr 'a-f' 'A-F')
  # " FFFE E000                    FDB     reset           RESET"
  line=$(grep -E "^ *$addr [0-9A-F]{4} +FDB " "$B/boot.lst" | head -1)
  lst=$(echo "$line" | awk '{print $2}')
  label=$(echo "$line" | awk '{print $4}')
  # " E000 4F              reset   clra" - the label's own definition
  def=$(grep -E "^ *[0-9A-F]{4} [0-9A-F]* +$label( |$)" "$B/boot.lst" | head -1 | awk '{print $1}')
  if [ -z "$line" ] || [ -z "$def" ] || [ "$img" != "$lst" ] || [ "$img" != "$def" ]; then
    echo "FAIL  $name vector: image \$$img, listing \$${lst:-?}, label '${label:-?}' at \$${def:-?}"
    fail=1
  fi
done
# And RESET is the ORG: machine.md 7.2 fetches the first instruction from $E000.
reset=$(od -An -v -tx1 -j 8190 -N 2 "$OUT/boot.bin" | tr -d ' \n' | tr 'a-f' 'A-F')
[ "$reset" = "E000" ] || { echo "FAIL  RESET vector is \$$reset, want \$E000"; fail=1; }
[ "$fail" -eq 0 ] || exit 1
echo "ok    boot.bin is 8192 bytes, and all seven vectors match the image, the listing and their labels (RESET = \$$reset)"
