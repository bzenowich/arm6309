#!/bin/sh
# Assemble v3boot.asm -- v3machine_tb's fixture ROM -- and emit what the
# simulation loads.
#
#   sh software/boot/v3boot/mkv3rom.sh         (from anywhere)
#
# Three outputs, in software/boot/v3boot/:
#   v3boot.bin   the raw 8 KB image -- ROM page 0
#   v3boot.hex   the same bytes as $readmemh records, for mainboard.v's `rom`
#   v3boot.lst   A09's listing, the only place the encodings are visible
#
# ⚠ THE ADDRESS MAPPING IS THE INTERESTING PART, and it is software/tools/
# mkrom.sh's word for word: in boot mode and in the vector page the '244 drives
# physical A20-A13 to zero, so the ROM byte a logical address reaches is
# `LA & $1FFF` -- and after RUN the block-7 entry points at the same physical
# page, so it is the same byte. The source ORGs at $E000 and the image is
# offset 0: logical $E000 IS ROM $0000 and logical $FFFE IS ROM $1FFE.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e

cd "$(dirname "$0")/../../.."          # the repository root
ROOT=$(pwd)
OUT="$ROOT/software/boot/build"
SRC="$ROOT/software/boot/v3boot"
mkdir -p "$OUT"
A09_DIR="${A09_DIR:-$(cd "$_here/../../.." && pwd)/.tools/a09}"

sh "$ROOT/software/tools/fetch-a09.sh" >/dev/null
A09="$A09_DIR/a09"

# ⛔ A09 EXITS 0 WITH ERRORS ON ITS STDOUT, and writes a .bin anyway - the same
# shape as CLAUDE.md's fitter trap ("a failed fit that leaves a CONVINCING
# one"). A branch out of range assembles as a hole in the image and the size
# check below still passes, so the assembler's own output is what decides.
log=$(mktemp)
trap 'rm -f "$log"' EXIT
"$A09" -B"$OUT/v3boot.bin" -L"$OUT/v3boot.lst" "$SRC/v3boot.asm" 2>&1 | tee "$log"
if grep -qi 'error' "$log"; then
  echo "FAIL  a09 reported errors (above)"
  exit 1
fi

size=$(wc -c < "$OUT/v3boot.bin")
if [ "$size" -ne 8192 ]; then
  echo "FAIL  v3boot.bin is $size bytes, want 8192 - the image must be ROM page 0 exactly"
  exit 1
fi

# $readmemh, one byte per line from address 0.
od -An -v -tx1 -w16 "$OUT/v3boot.bin" | tr -s ' ' '\n' | grep -v '^$' > "$OUT/v3boot.hex"
lines=$(wc -l < "$OUT/v3boot.hex")
[ "$lines" -eq 8192 ] || { echo "FAIL  v3boot.hex has $lines records, want 8192"; exit 1; }

# The two vectors this fixture depends on, compared rather than printed
# (mkrom.sh's own trap: it used to print the reset vector without comparing it
# to anything, so a mis-assembled vector read as a claim).
reset=$(od -An -v -tx1 -j 8190 -N 2 "$OUT/v3boot.bin" | tr -d ' \n' | tr 'a-f' 'A-F')
irq=$(od -An -v -tx1 -j 8184 -N 2 "$OUT/v3boot.bin" | tr -d ' \n' | tr 'a-f' 'A-F')
irqdef=$(grep -E "^ *[0-9A-F]{4} [0-9A-F]* +irqh( |$)" "$OUT/v3boot.lst" | head -1 | awk '{print $1}')
fail=0
[ "$reset" = "E000" ] || { echo "FAIL  RESET vector is \$$reset, want \$E000"; fail=1; }
[ -n "$irqdef" ] && [ "$irq" = "$irqdef" ] || {
  echo "FAIL  IRQ vector is \$$irq, and irqh is at \$${irqdef:-?}"; fail=1; }
[ "$fail" -eq 0 ] || exit 1
echo "ok    v3boot.bin is 8192 bytes; RESET = \$$reset and IRQ = \$$irq, which is irqh"
