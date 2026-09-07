#!/bin/sh -e
# Compile a .pld with Atmel's own CUPL and drop the result in
# ../jedec/reference/, which is what jedec/cupl.check.ts validates against.
#
# THE RULE THIS EXISTS FOR: a GAL does not ship without a CUPL reference.
# Our assembler and our fuse-map simulator share one device description, so
# they agree with each other whatever it says - that is how two errors survived
# 178 passing checks on 2026-09-07. The only thing that breaks the tie is a
# second implementation.
#
# Needs the CUPL extracted by extract-wincupl.sh.
#
# Usage: cupl-reference.sh ../mmu.pld [device]     (device defaults to g22v10)

PLD=${1:?usage: cupl-reference.sh path/to/name.pld [device]}
DEVICE=${2:-g22v10}
SHARED=${SHARED:-$HOME/.wine_atf/drive_c/Wincupl/Shared}
REF=$(cd "$(dirname "$0")/../jedec" && pwd)/reference

[ -f "$SHARED/cupl.exe" ] || { echo "no cupl.exe in $SHARED - run extract-wincupl.sh" >&2; exit 1; }

export WINEPREFIX=${WINEPREFIX:-$HOME/.wine_atf}
export WINEDEBUG=-all
export LIBCUPL="$SHARED/cupl.dl"

name=$(basename "$PLD" .pld)
cp "$PLD" "$SHARED/"
( cd "$SHARED" && wine cupl.exe -j -n -x -f -l "$DEVICE" "$name" ) | tail -3

[ -f "$SHARED/$name.jed" ] || { echo "CUPL produced no JEDEC; see $SHARED/$name.lst" >&2; exit 1; }
mkdir -p "$REF"
cp "$SHARED/$name.jed" "$REF/$name.cupl.jed"
echo "wrote $REF/$name.cupl.jed"
echo
echo "Regenerating an existing reference should change only the Created line and"
echo "the trailing transmission checksum that covers it - CUPL is deterministic,"
echo "so any diff in the *L fuse lines means the .pld changed. Revert if it is"
echo "only the timestamp; the file is kept byte-exact as Atmel emitted it."
echo
echo "For a NEW part: add it to the REGISTRY in ../jedec/cupl.check.ts and write"
echo "the comparison against its model. The registry FAILS the build for any"
echo "live GAL with no reference, which is the point."
