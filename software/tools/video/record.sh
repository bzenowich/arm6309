#!/bin/sh
# record.sh OUT - run one scene on the host emulator and keep every frame.
#
# The first half of every program's demo video (software/<program>/video/
# run-video.sh); clip.py is the second.  It boots NitrOS-9 off the system card
# exactly as the benches do, types LINES at the serial shell, and records
# OUT/frames.bin, OUT/serial.out (+ serial.times) and OUT/console.txt.
#
#   LINES     what is typed, printf-escaped, lines ending \r        (required)
#   SECS      machine seconds to run                                (default 120)
#   GATE      serial text that starts the typing                    (default "02}")
#   STOP      serial text that ends the run early                   (default DONE-arm6309)
#   PS2FILE   a PS2_SCRIPT for the mouse and keyboard - not PS2, which is the
#             shell's own continuation prompt ("> ") and is always set
#   PS2_GATE  the serial text that script is timed from             (default DESK-READY)
#   ROMDIR    the NitrOS-9 ROM and system card to boot    (default software/nitros9/build/rom,
#             rebuilt by mkrom.sh on every run unless NOBUILD=1)
#   SDIMG     a card image other than ROMDIR/system.img
#   CARD_DATA files a program reads off /SD0/DATA that the general card does not
#             carry (stardew's 480 KB picture), and CARD_DEMOS the programs: with
#             these a card of its own is built, OUT/sd.img, as the program's bench does
#   EMUENV    anything else for the emulator, e.g. "MARKS=1104"
#
# ⚠ It needs ../nitros9 on its arm6309 branch (NITROS9DIR=...) to build the
# ROM, like every software bench.  A recording is ~70 KB a frame: a 150 s run
# is several hundred MB, which is why clip.py deletes it unless KEEP=1.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
ROOT=$(cd "$_here/../../.." && pwd)
OUT=${1:?usage: record.sh OUT}
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
[ -n "$LINES" ] || { echo "FAIL  record.sh: no LINES to type"; exit 1; }
SECS=${SECS:-120}
ROMDIR=${ROMDIR:-$ROOT/software/nitros9/build/rom}

# ---- the ROM and the card: the NitrOS-9 component's build output ---------
# ⛔ REBUILT EVERY TIME, as every bench does: a ROM that exists is not a ROM
# that is current, and a card built before a program was renamed or retired
# records a machine that no longer exists.  The recipe's make is incremental,
# so a rebuild with nothing changed is quick.  NOBUILD=1 uses what is there.
# ⚠ One recording at a time: two builds in ../nitros9's recipe directory at
# once write the same modules.
if [ -z "$NOBUILD" ]; then
  echo "      building the ROM and the system card into $ROMDIR"
  sh "$ROOT/software/nitros9/mkrom.sh" "$ROMDIR" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$ROMDIR/arm6309_rom.bin" ] && [ -f "$ROMDIR/system.img" ] || {
  echo "FAIL  no ROM and card in $ROMDIR"; exit 1; }
if [ -n "$CARD_DATA" ]; then
  D="$OUT/carddata"; rm -rf "$D"; mkdir -p "$D"
  for f in $CARD_DATA; do cp "$f" "$D/" || { echo "FAIL  no $f"; exit 1; }; done
  OUT="$ROMDIR" DATA="$D" sh "$ROOT/software/nitros9/mksyscard.sh" "$OUT/sd.img" ${CARD_DEMOS:?CARD_DATA needs CARD_DEMOS} \
    > "$OUT/card.log" 2>&1 || { tail -8 "$OUT/card.log"; echo "FAIL  the card did not build"; exit 1; }
  SDIMG="$OUT/sd.img"
fi
SDIMG=${SDIMG:-$ROMDIR/system.img}

# ---- the emulator ----------------------------------------------------------
cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" \
   "$ROOT/software/emu/machine.c" "$ROOT/hardware/cpu/sim/cpu6809.c" \
   "$ROOT/hardware/cpu/sim/hd6309.c" "$ROOT/hardware/audio/refplayer/card.c"

# ---- the run ---------------------------------------------------------------
# ⚠ CR, not LF, between lines: the shell's line editor ends a line on CR
# (hardware/video3/docs/demo-report.md 15.3).
printf "$LINES" > "$OUT/typed.txt"
rm -f "$OUT/frames.bin"
STOPTXT=$(printf '\n%s' "${STOP:-DONE-arm6309}")
PS2ARGS=""
if [ -n "$PS2FILE" ]; then
  [ -f "$PS2FILE" ] || { echo "FAIL  no PS/2 script $PS2FILE"; exit 1; }
  PS2ARGS="PS2_SCRIPT=$PS2FILE PS2_SCRIPT_GATE=${PS2_GATE:-DESK-READY}"
fi
echo "      recording $SECS s of machine time into $OUT"
( cd "$OUT" && env SERIAL_IN=typed.txt SERIAL_GATE="${GATE:-02\}}" SERIAL_TYPE=60 \
    SERIAL_THINK=700 SERIAL_STOP="$STOPTXT" WILD=1 VIDEO3=1 SDIMG="$SDIMG" \
    SERIAL_TIMES=serial.times KEEPFRAMES=1 $PS2ARGS $EMUENV \
    ./emu "$ROMDIR/arm6309_rom.bin" . "$SECS" > /dev/null 2> emu.log ) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
sed 's/\x1b\[[0-9;]*m//g' "$OUT/emu.log" > "$OUT/emu.txt"

[ -s "$OUT/frames.bin" ] || { tail -5 "$OUT/emu.txt"; echo "FAIL  no frames were recorded"; exit 1; }
if grep -q '^WILD' "$OUT/emu.txt"; then
  grep -m3 '^WILD' "$OUT/emu.txt"; echo "FAIL  the CPU ran through empty RAM"; exit 1
fi
echo "ok    recorded $(grep -o 'emu: [0-9]* frames' "$OUT/emu.txt" | tail -1 | cut -d' ' -f2) frames"
