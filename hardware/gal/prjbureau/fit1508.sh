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
# Delete the previous run's outputs FIRST. The .tt2 check below is the only
# thing standing between a CUPL error and a silently stale place-and-route,
# and without this it passes on yesterday's file. That is not hypothetical:
# it fitted a design two revisions old, reported success, and the only tell
# was a signal name in the .fit that no longer existed in the .pld.
rm -f "$SHARED/$name".*
cp "$PLD" "$SHARED/"
( cd "$SHARED" && wine cupl.exe -j -n -x -f -l -u atmel.dl f1508ispplcc84 "$name" ) | tail -2
[ -f "$SHARED/$name.tt2" ] || { echo "CUPL produced no .tt2; see $SHARED/$name.lst" >&2; exit 1; }

rm -f "$FITTERS/$name".*
cp "$SHARED/$name.tt2" "$FITTERS/"
# JTAG=on reserves TMS/TDI/TDO/TCK so the part can be programmed in circuit.
# It costs four I/O, so it is a fit result and not a preference: ask for it and
# read whether the design still fits.
JTAG=${JTAG:-off}
# ⛔ THE SUCCESS TEST IS THE FITTER'S OWN SENTENCE, NOT THE PRESENCE OF A
# JEDEC, and that distinction cost an afternoon on 2026-09-10. `fit1508.exe`
# answered `INTERNAL ERROR - Please contact your Hot-Line` for a design that
# does not fit AND WROTE A .jed AND A .fit ANYWAY - so the file test below
# passed, this script printed "wrote ...", and the .fit it copied out reported
# a plausible 128/128 cells and a BETTER LAB fan-in than the design that really
# did fit. A failed fit that leaves no output is CLAUDE.md's first trap; this
# is its nastier sibling, a failed fit that leaves a CONVINCING one.
#
# "Design fits successfully" appears only in the fitter's stdout - it is not in
# the .fit report, so nothing downstream can recover it. It has to be caught
# here.
fitlog=$(cd "$FITTERS" && wine fit1508.exe "$name.tt2" -device "$DEV" \
    -preassign ignore -strategy JTAG="$JTAG" 2>&1)
echo "$fitlog" | grep -viE '^warning' | tail -6

case "$fitlog" in
  *"INTERNAL ERROR"*)
    echo "fitter reported INTERNAL ERROR - the design does not fit; see $FITTERS/$name.fit" >&2
    exit 1 ;;
esac
echo "$fitlog" | grep -q "Design fits successfully" || {
  echo "fitter never said 'Design fits successfully'; see $FITTERS/$name.fit" >&2
  exit 1
}
[ -f "$FITTERS/$name.jed" ] || { echo "fitter produced no JEDEC; see $FITTERS/$name.fit" >&2; exit 1; }
mkdir -p "$OUT"
cp "$FITTERS/$name.jed" "$FITTERS/$name.fit" "$OUT/"
echo "wrote $OUT/$name.jed and $name.fit"
