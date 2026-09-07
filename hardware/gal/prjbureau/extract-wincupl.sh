#!/bin/sh -e
# Extract the ATF15xx fitters and the CUPL compiler from Microchip's WinCUPL
# installer, on Linux, without root and without running the GUI.
#
# What this is for: fit1508.exe is what prjbureau's fuzzers drive, and cupl.exe
# is what produced jedec/reference/*.cupl.jed - the reference JEDECs that found
# two errors in our own fuse map. See ../jedec/cupl.check.ts.
#
# Three things about this that were not obvious:
#
#   * Wine 9 runs the 32-bit installer with no wine32 and no i386 multiarch -
#     WoW64 is built in. The earlier claim in this directory that i386 was
#     required was wrong.
#   * The installer needs a display and there is none here, but it extracts its
#     MSI payload to the Wine prefix's Temp BEFORE it fails, which is enough.
#   * 7-Zip cannot open the payload cabinet if you carve it out of the .exe by
#     byte offset: MSI streams are stored in non-contiguous 4 KB sectors, so
#     the bytes are not consecutive. Extract it from the MSI instead.
#
# Usage: extract-wincupl.sh /path/to/awincupl.exe.zip [destination]

ZIP=${1:?usage: extract-wincupl.sh awincupl.exe.zip [dest]}
DEST=${2:-$HOME/.wine_atf/drive_c/Wincupl}
WORK=$(mktemp -d)
export WINEPREFIX=${WINEPREFIX:-$HOME/.wine_atf}
export WINEDEBUG=-all

unzip -o -q "$ZIP" -d "$WORK"

# Let the installer self-extract. It will fail at the GUI; that is expected and
# it has already written WinCupl.msi to Temp by then.
( cd "$WORK" && wine awincupl.exe /s /v"/qn" >/dev/null 2>&1 || true )

MSI=$(find "$WINEPREFIX/drive_c/users" -name WinCupl.msi -print -quit)
[ -n "$MSI" ] || { echo "WinCupl.msi not found - did the installer run at all?" >&2; exit 1; }

7z e -y -o"$WORK/msi" "$MSI" Data1.cab >/dev/null
7z e -y -o"$WORK/cab" "$WORK/msi/Data1.cab" >/dev/null

mkdir -p "$DEST/Fitters" "$DEST/Shared"
cp "$WORK/cab"/fit150*.exe "$WORK/cab"/FIT1500.EXE "$WORK/cab"/atmel.std "$DEST/Fitters/"
# 7-Zip appends a digit where the cabinet holds two files of the same name.
for f in cupl.exe cupl.dl Atmel.dl cupla.dll cuplb.dll cuplc.dll \
         cuplk.dll cuplm.dll cuplx.dll csima.dll csimk.dll vsima.dll CuplErr.txt; do
    cp "$WORK/cab/$f1" "$DEST/Shared/$f" 2>/dev/null ||
    cp "$WORK/cab/${f}1" "$DEST/Shared/$f" 2>/dev/null ||
    cp "$WORK/cab/$f"  "$DEST/Shared/$f" 2>/dev/null || true
done
rm -rf "$WORK"

echo "fitters and CUPL in $DEST"
( cd "$DEST/Fitters" && wine fit1508.exe 2>/dev/null | head -1 )
