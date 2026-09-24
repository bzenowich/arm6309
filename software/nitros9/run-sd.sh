#!/bin/sh
# NitrOS-9 Level 2 on the host emulator, with an SD card in the socket:
# boot, mount /SD0, read a file off it, write one to it, and read it back.
#
#   sh software/nitros9/run-sd.sh               (from the repository root)
#   NOBUILD=1 sh software/nitros9/run-sd.sh     (use the ROM already built)
#   OUT=dir   overrides /tmp/arm6309-sd
#
# ⚠ WHAT THIS EXERCISES that software/emu/test/run-sdtest.sh does not:
# that test drives the card's registers from C and proves the MODEL is the
# card.  This one puts NitrOS-9's RBF, the rbsd driver and a real filesystem
# on top and asks whether the whole stack works - 9.4.1's deblocking against
# a 256-byte sector, the one-block cache, and read-modify-write on every
# directory and bitmap update.
#
# ⛔ The exit code is the answer.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/." && pwd)/build/sd}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-120}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
mkdir -p "$OUT"
PATH="$TOOLS:$PATH"
export PATH

if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { tail -20 "$OUT/mkrom.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
# ⛔ THE CARD IS THE SYSTEM DISK and the ROM is a video3 ROM, both since
# 2026-09-22: without SDIMG the machine does not boot, and without VIDEO3 the
# emulator runs the archived card's model against CoArm's video3 poll and
# hangs (run-emu.sh says the rest).
export VIDEO3=1
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

# ⭐ THE MEDIA IS MADE BY THE TOOLCHAIN AND NOT BY THE MACHINE, which is the
# point: an image the host's os9 tools wrote and the machine can read is two
# independent implementations of RBF agreeing, the same discipline the video
# benches keep.  4 MB of 256-byte sectors - and 4,194,304 is a whole number of
# 512-byte SD blocks, which it has to be.
# ⛔ AND IT IS THE SYSTEM CARD SINCE 2026-09-22.  There is one socket, the ROM
# carries no filesystem, and the machine boots from what is in it - so "a
# formatted volume the host wrote, reached by name as a SECOND drive" is not a
# state this machine has any more.  What is still worth asserting is the half
# `run-sdboot.sh` does not: the driver's WRITE path, RBF's read-modify-write of
# a directory entry and the allocation bitmap (sdcard.md §9.4.1), and that what
# the machine wrote is on the image the HOST reads back.
#
# ⭐ So the bench's own file rides on the system card, in its DATA directory,
# and the host's os9 tools put it there - which keeps the two-implementations
# discipline that was the point of formatting one here.
IMG="$OUT/sd.img"
rm -f "$IMG"
SD="$OUT/carddata"
rm -rf "$SD"; mkdir -p "$SD"
printf 'the storage card works\n' > "$SD/HELLO.TXT"
OUT="$OUT" DATA="$SD" NAME="arm6309 SD" \
  sh software/nitros9/mksyscard.sh "$IMG" > "$OUT/format.log" 2>&1 || {
    cat "$OUT/format.log"; echo "FAIL  the system card did not build"; exit 1; }

cc -O2 -Wall -Ihardware/audio/refplayer -o "$OUT/emu" software/emu/machine.c software/emu/cpu6809.c software/emu/hd6309.c hardware/audio/refplayer/card.c

# ⚠ /SD0 IS THE BOOT DEVICE NOW, and /DD is the same disk under its other
# name.  `free` reads the allocation bitmap, `list` a file's data sectors, and
# the `merge >` writes: a new file is a directory entry and a bitmap update,
# which is §9.4.1's read-modify-write path and the card's worst.
printf 'dir /sd0/DATA\rfree /sd0\rlist /sd0/DATA/HELLO.TXT\rmerge /sd0/DATA/HELLO.TXT >/sd0/DATA/COPY.TXT\rdir /sd0/DATA\rlist /sd0/DATA/COPY.TXT\rdel /sd0/DATA/COPY.TXT\rdir /sd0/DATA\recho DONE-arm6309-sd\r' > "$OUT/typed.txt"
STOP=$(printf '\nDONE-arm6309-sd')
(cd "$OUT" && SDIMG=sd.img SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" WILD=1 \
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
claim "⭐ dir /sd0/DATA read the directory the host tools wrote" has '^HELLO.TXT'
claim "free /sd0 read the volume header the host tools wrote"  has '\"arm6309 SD\" created'
# ⛔ AGAINST THE IMAGE, NOT A LITERAL.  The card is `mksyscard.sh`'s now and
# its size is whatever the system plus the DATA came to, so a hard-coded
# figure here is a claim about the build and not about DD.TOT.  What the claim
# IS: the sector count the machine printed is the one in the image's own LSN 0
# (+$00..$02, big-endian), which is the media's size and not the descriptor's.
# ⛔ AND THE GROUPING IS DONE WITH sed, NOT `printf "%'d"`: dash has no such
# directive and answers `printf: %': invalid directive` on stderr, leaving the
# expansion EMPTY - so the pattern became "Capacity:  sectors", matched
# nothing, and the claim failed while the machine was perfectly right.
tot=$(od -An -v -tu1 -j0 -N3 "$IMG" | awk '{print $1*65536 + $2*256 + $3}')
totc=$(echo "$tot" | sed ':a;s/\B[0-9]\{3\}\>/,&/;ta')
claim "   and DD.TOT off LSN 0: the media's $totc sectors, not the descriptor's" \
  has "Capacity: $totc sectors"
claim "⭐ list read a file's data off the card"              has 'the storage card works'
claim "⭐ a new file was WRITTEN - read-modify-write, 9.4.1" has 'COPY.TXT'
claim "   and reading it back gives what went in"            test "$(grep -c 'the storage card works' "$OUT/console.txt")" -ge 2
claim "the run ended at the last command, not by the clock"  grep -q 'SERIAL_STOP seen' "$OUT/emu.log"
claim "no crash: nothing printed D.Crash's '!'"  sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/console.txt'"
claim "and the driver never reported a hardware error"       sh -c "! grep -qi 'error #24[0-9]' '$OUT/console.txt'"

# ⭐ THE GATE THAT IS NOT THE CONSOLE: the host tools read the image back and
# must find what the machine wrote.  A driver that writes to the cache and
# never to the card passes every claim above and fails this one.
os9 dir "$IMG,DATA" > "$OUT/after.txt" 2>&1 || true
claim "⛔ and the HOST sees the deletion the machine made - the write reached the card" \
  sh -c "! grep -q 'COPY.TXT' '$OUT/after.txt'"

# ⭐ THE NEGATIVE CONTROL, and without it every claim above is untethered:
# the same ROM, the same typed commands, and NO CARD IN THE SOCKET.  ⛔ It
# used to mean "the machine boots off the ROM and /SD0 refuses at §9.0";
# since 2026-09-22 it means the machine NEVER REACHES A SHELL, because there
# is nothing else to boot.  Either way a driver that "worked" here would mean
# the reads above never touched the card at all.
# ⚠ `software/nitros9/run-sdboot.sh` is where the three card states are
# asserted from reset; this is the cheap version that keeps THIS bench honest.
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_AT=8 SERIAL_STOP="$STOP" \
   ./emu "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu-nocard.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/nocard.txt"
nohas() { ! grep -q -- "$1" "$OUT/nocard.txt"; }

claim "⛔ with an EMPTY socket the machine NEVER REACHES A SHELL" \
  sh -c "! grep -q -- '/DD:' '$OUT/nocard.txt'"
claim "⛔ and boot_sd said why: no system disk (tb n)"        grep -q 'tbn' "$OUT/nocard.txt"
claim "⛔ and serves NO data: the file's contents never appear" \
  sh -c "! grep -q 'the storage card works' '$OUT/nocard.txt'"
claim "⛔ and no directory came from anywhere else"           sh -c "! grep -q '^HELLO.TXT' '$OUT/nocard.txt'"
claim "⛔ and it FAILS rather than hanging - the run reached its own clock" \
  sh -c "! grep -q 'SERIAL_STOP seen' '$OUT/emu-nocard.log'"

echo ""
echo "      $n claims, $fail failed"
[ "$fail" -eq 0 ] || exit 1
