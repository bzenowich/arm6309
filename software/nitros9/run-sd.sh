#!/bin/sh
# NitrOS-9 Level 2 on the host emulator, with an SD card in the socket:
# boot, mount /SD0, read a file off it, write one to it, and read it back.
#
#   sh software/nitros9/run-sd.sh               (from the repository root)
#   NOBUILD=1 sh software/nitros9/run-sd.sh     (use the ROM already built)
#   OUT=dir   overrides /tmp/arm6309-sd
#
# ⚠ WHAT THIS EXERCISES that software/demo/emu/test/run-sdtest.sh does not:
# that test drives the card's registers from C and proves the MODEL is the
# card.  This one puts NitrOS-9's RBF, the rbsd driver and a real filesystem
# on top and asks whether the whole stack works - 9.4.1's deblocking against
# a 256-byte sector, the one-block cache, and read-modify-write on every
# directory and bitmap update.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-sd}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-120}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
mkdir -p "$OUT"
PATH="$TOOLS:$PATH"
export PATH

if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { tail -20 "$OUT/mkrom.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

# ⭐ THE MEDIA IS MADE BY THE TOOLCHAIN AND NOT BY THE MACHINE, which is the
# point: an image the host's os9 tools wrote and the machine can read is two
# independent implementations of RBF agreeing, the same discipline the video
# benches keep.  4 MB of 256-byte sectors - and 4,194,304 is a whole number of
# 512-byte SD blocks, which it has to be.
IMG="$OUT/sd.img"
rm -f "$IMG"
os9 format -e -l16384 "$IMG" -n"arm6309 SD" > "$OUT/format.log" 2>&1
printf 'the storage card works\n' > "$OUT/hello.txt"
os9 copy -l "$OUT/hello.txt" "$IMG,HELLO.TXT" >> "$OUT/format.log" 2>&1
os9 makdir "$IMG,SUB" >> "$OUT/format.log" 2>&1

cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c audio/refplayer/card.c

# /SD0 is not the boot device - /DD is still the ROM disk - so the card is
# reached by name.  `free` reads the allocation bitmap, `list` a file's data
# sectors, and the `merge >` writes: a new file is a directory entry and a
# bitmap update, which is 9.4.1's read-modify-write path and the card's worst.
printf 'dir /sd0\rfree /sd0\rlist /sd0/HELLO.TXT\rmerge /sd0/HELLO.TXT >/sd0/COPY.TXT\rdir /sd0\rlist /sd0/COPY.TXT\rdel /sd0/COPY.TXT\rdir /sd0\recho DONE-arm6309-sd\r' > "$OUT/typed.txt"
STOP=$(printf '\nDONE-arm6309-sd')
(cd "$OUT" && SDIMG=sd.img SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" \
   ./emu "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"

fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }
has() { grep -q -- "$1" "$OUT/console.txt"; }

claim "the machine booted to a shell"                        has '/DD:'
claim "the bootfile carries rbsd and its SD0 descriptor"     has 'rbsd'
# ⚠ ANCHORED, because the typed command line is echoed to the console too:
# a bare grep for HELLO.TXT matches `list /sd0/HELLO.TXT` being typed and
# would pass with no card in the socket.  The negative control below caught
# exactly that, which is what a negative control is for.
claim "⭐ dir /sd0 read LSN 0 and the root the host tools wrote" has '^HELLO.TXT  *SUB'
claim "free /sd0 read the volume header the host tools wrote"  has '\"arm6309 SD\" created'
claim "   and DD.TOT off LSN 0: the media's size, not the descriptor's" has 'Capacity: 16,384 sectors'
claim "⭐ list read a file's data off the card"              has 'the storage card works'
claim "⭐ a new file was WRITTEN - read-modify-write, 9.4.1" has 'COPY.TXT'
claim "   and reading it back gives what went in"            test "$(grep -c 'the storage card works' "$OUT/console.txt")" -ge 2
claim "the run ended at the last command, not by the clock"  grep -q 'SERIAL_STOP seen' "$OUT/emu.log"
claim "no crash: nothing printed D.Crash's '!'"  sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/console.txt'"
claim "and the driver never reported a hardware error"       sh -c "! grep -qi 'error #24[0-9]' '$OUT/console.txt'"

# ⭐ THE GATE THAT IS NOT THE CONSOLE: the host tools read the image back and
# must find what the machine wrote.  A driver that writes to the cache and
# never to the card passes every claim above and fails this one.
os9 dir "$IMG" > "$OUT/after.txt" 2>&1 || true
claim "⛔ and the HOST sees the deletion the machine made - the write reached the card" \
  sh -c "! grep -q 'COPY.TXT' '$OUT/after.txt'"

# ⭐ THE NEGATIVE CONTROL, and without it every claim above is untethered:
# the same ROM, the same typed commands, and NO CARD IN THE SOCKET.  The
# emulator reports CD = 0 when SDIMG is unset, Init must refuse at 9.0, and
# /SD0 must then fail rather than quietly serving bytes from somewhere else.
# ⛔ A driver that "worked" here would mean the reads above never touched the
# card at all.
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" \
   ./emu "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu-nocard.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/nocard.txt"
nohas() { ! grep -q -- "$1" "$OUT/nocard.txt"; }

claim "⛔ with an EMPTY socket the machine still boots"       grep -q '/DD:' "$OUT/nocard.txt"
claim "⛔ and /SD0 refuses at 9.0 - E\$NotRdy, not silence"   grep -q 'Error #246' "$OUT/nocard.txt"
claim "⛔ and serves NO data: the file's contents never appear" \
  sh -c "! grep -q 'the storage card works' '$OUT/nocard.txt'"
claim "⛔ and no directory came from anywhere else"           sh -c "! grep -q '^HELLO.TXT' '$OUT/nocard.txt'"
claim "⛔ and it FAILS rather than hanging - the run reached the end" \
  grep -q 'SERIAL_STOP seen' "$OUT/emu-nocard.log"

echo ""
echo "      $n claims, $fail failed"
[ "$fail" -eq 0 ] || exit 1
