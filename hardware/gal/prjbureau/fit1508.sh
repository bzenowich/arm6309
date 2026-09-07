#!/bin/sh -e
# Compile a generated .pld for an ATF1508AS and place-and-route it, on Linux.
#
# The .pld is generated from the same term lists the GAL checks exercise
# (jedec/cupl.ts), so the CPLD and the 22V10 fits have one origin. This script
# is the half that is not ours: cupl.exe turns equations into a Berkeley PLA,
# and fit1508.exe places and routes. jedec/README.md explains why we do not
# reimplement the second half.
#
# Four things that cost an afternoon to find:
#
#   * Use atmel.dl, not cupl.dl. The ATF devices are only in the former, and
#     the device name is f1508ispplcc84 (or f1508plcc84 without JTAG).
#   * Do NOT emit .sp. A GAL22V10 has a synchronous preset shared by every
#     macrocell; an ATF1508AS has none. CUPL emits a .P output per register
#     anyway, the fitter says "Warning - .P extension unknown" once per
#     register, and counts every one as another output it must place. That
#     alone is the difference between "Design has 91 IOs" and fitting.
#   * Only REGISTERED internal signals need PINNODE. A combinational one is an
#     ordinary CUPL intermediate: substituted where it is read, no macrocell,
#     no pin. Declaring those as PINNODE spends pins on nothing.
#   * Registered nodes need an explicit .ck. A 22V10 has one clock on pin 1 and
#     CUPL infers it; an ATF1508AS has three and the fitter refuses to guess.
#
# Usage: fit1508.sh ../audio.pld [device]

PLD=${1:?usage: fit1508.sh path/to/name.pld [P1508C84]}
DEV=${2:-P1508C84}
SHARED=${SHARED:-$HOME/.wine_atf/drive_c/Wincupl/Shared}
FITTERS=${FITTERS:-$HOME/.wine_atf/drive_c/Wincupl/Fitters}
OUT=$(cd "$(dirname "$0")/../cpld" && pwd)

[ -f "$SHARED/cupl.exe" ] || { echo "run extract-wincupl.sh first" >&2; exit 1; }
export WINEPREFIX=${WINEPREFIX:-$HOME/.wine_atf}
export WINEDEBUG=-all
export LIBCUPL="$SHARED/atmel.dl"
export PATH="$FITTERS:$PATH"

name=$(basename "$PLD" .pld)
cp "$PLD" "$SHARED/"
( cd "$SHARED" && wine cupl.exe -j -n -x -f -l -u atmel.dl f1508ispplcc84 "$name" ) | tail -2
[ -f "$SHARED/$name.tt2" ] || { echo "CUPL produced no .tt2; see $SHARED/$name.lst" >&2; exit 1; }

rm -f "$FITTERS/$name".*
cp "$SHARED/$name.tt2" "$FITTERS/"
( cd "$FITTERS" && wine fit1508.exe "$name.tt2" -device "$DEV" -preassign ignore ) \
  | grep -viE '^warning' | tail -6

[ -f "$FITTERS/$name.jed" ] || { echo "fitter produced no JEDEC; see $FITTERS/$name.fit" >&2; exit 1; }
mkdir -p "$OUT"
cp "$FITTERS/$name.jed" "$FITTERS/$name.fit" "$OUT/"
echo "wrote $OUT/$name.jed and $name.fit"
