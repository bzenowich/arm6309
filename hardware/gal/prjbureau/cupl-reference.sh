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
# ⭐ THE WINE PREFIX LIVES IN THE REPOSITORY, NOT IN $HOME - 2026-09-10.
#
# This project is developed inside a bwrap sandbox whose $HOME does not survive
# the session, so a prefix under ~/.wine_atf is extracted, used once, and gone -
# and its absence is SILENT, because `npm run check` passes without a fitter and
# only the fit knows whether a design still fits the part. Keeping it beside the
# sources makes it as durable as they are.
#
# ⚠ IT IS 1.3 GB AND GITIGNORED. It is a Wine prefix with Microchip's WinCUPL
# inside it; nothing here may be redistributed, and extract-wincupl.sh rebuilds
# it from awincupl.exe.zip in about a minute.
#
# $ATF_HOME overrides it; $WINEPREFIX, $SHARED and $FITTERS still override that,
# so an existing prefix elsewhere keeps working.
ATF_HOME=${ATF_HOME:-$(cd "$(dirname "$0")/../../.." && pwd)/.wine_atf}

SHARED=${SHARED:-$ATF_HOME/drive_c/Wincupl/Shared}
REF=$(cd "$(dirname "$0")/../jedec" && pwd)/reference

[ -f "$SHARED/cupl.exe" ] || { echo "no cupl.exe in $SHARED - run extract-wincupl.sh" >&2; exit 1; }

export WINEPREFIX=${WINEPREFIX:-$ATF_HOME}
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
