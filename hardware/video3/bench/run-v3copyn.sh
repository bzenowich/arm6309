#!/bin/sh
# ⛔ DOES SS.CopyN COPY THE RIGHT PIXELS?  Nothing asked until now.
#
#   sh hardware/video3/bench/run-v3copyn.sh          OUT=dir overrides
#
# SS.CopyN walks a table of rectangles in one call instead of one call a
# rectangle (vidcpy3.asm's DoCopyN).  v3cpyb TIMES it, which says nothing
# about where the pixels land: an off-by-one in the walk, a dropped last
# entry or a stale block would leave every measurement honest and every
# frame wrong.
#
# ⭐ So this runs the SAME n rectangles twice - once as one SS.CopyN table,
# once as n separate SS.Copy calls - into a screen cleared the same way each
# time, and dumps VRAM after each.  The two must be identical, byte for byte.
# ⚠ The rectangles DIFFER from each other (v3cpyb's FanSet fans them out in
# both axes), because a table of identical entries cannot tell a walk that
# repeats one block from a walk that reads them all.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/v3copyn}
N=${N:-24}
rm -rf "$OUT"; mkdir -p "$OUT/sys"

python3 software/toolbox/bench/mkv3text.py "$OUT/sys" > "$OUT/mk.log" || { cat "$OUT/mk.log"; exit 1; }
# ⚠ CMDS_EXTRA: the demos live on an SD card now (software/nitros9/mksddisk.sh);
# this bench boots with an empty socket, so it asks for v3cpyb by name.
CMDS_EXTRA=v3cpyb sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
# ⛔ THE CARD IS THE SYSTEM DISK since 2026-09-22 (arm6309 docs/history.md):
# the ROM carries the toolbox and no filesystem, so a session with an EMPTY
# SOCKET does not reach a shell at all.  mkrom.sh writes system.img beside the
# ROM out of the same build, and /DD is that card - which is why the
# `copy /dd/sys/...` lines below still read what SYSROM/$OUT/sys put there.
SDIMG="$OUT/system.img"; export SDIMG
[ -f "$SDIMG" ] || { echo "FAIL  no $SDIMG - mkrom.sh should have built the system card"; exit 1; }
cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

# ⚠ CR, not LF (demo-report.md §15.3).  Each pass starts from the same
# cleared screen, so the only difference can be the copies themselves.
run() {                     # run MODE OUTFILE
  printf 'iniz w5\rcopy /dd/sys/v3tset /w5\rv3cpyb %d 40 24 %d >/w5\recho DONE-arm6309\r' "$N" "$1" > "$OUT/typed.txt"
  STOP=$(printf '\nDONE-arm6309')
  (cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 VRAMDUMP="$2" \
     ./emu arm6309_rom.bin . 300 > /dev/null 2> "emu-$1.log") || true
  grep -q "SERIAL_STOP seen" "$OUT/emu-$1.log" || { echo "FAIL  mode $1 did not finish"; exit 1; }
  tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console-$1.txt"
  if grep -n "Error #" "$OUT/console-$1.txt"; then echo "FAIL  mode $1: a command failed"; exit 1; fi
}

run 2 list.bin
run 3 one.bin

python3 hardware/video3/bench/checkv3copyn.py "$OUT" "$N"
