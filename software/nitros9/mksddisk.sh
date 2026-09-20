#!/bin/sh
# ⭐ THE DEMO SD CARD: an RBF image the host's os9 tools write and the machine
# reads through rbsd (storage/docs/sdcard.md §9.4).
#
#   sh software/nitros9/mksddisk.sh /tmp/x/demos.img              every demo
#   sh software/nitros9/mksddisk.sh /tmp/x/demos.img mvania       just one
#   DATA=/tmp/x/data sh software/nitros9/mksddisk.sh ...          ⭐ with its data
#   MODS=dir  NAME="..."  SLACK=sectors  ...
#
# ⭐ CMDS AND DATA, and both halves moved.  CMDS is the demo PROGRAMS; DATA is
# what they open - the Haiku desktop and Paint's streams, the BBS, the
# overworld's world, the console faces.  software/nitros9/mkrom.sh writes the
# whole data set to $OUT/data and DATA= points here at it; the ROM disk's
# /DD/SYS keeps errmsg and nothing else.
#
# Since 2026-09-20 neither the demo programs nor their data are in the boot
# ROM's ROM disk (nitros9 recipes/arm6309/arm6309.mak): the ROM is the kernel,
# the shell, the shared modules, errmsg and a rescue command set, and the
# applications live here.  /DD/SYS alone used to be 1,140 of the image's
# 1,952 sectors.
#
# ⭐ THE IMAGE IS WRITTEN BY THE TOOLCHAIN AND READ BY THE MACHINE, which is
# the point, and the same discipline run-sd.sh keeps: two independent
# implementations of RBF have to agree or nothing loads.
#
# ⚠ THE LENGTH IS A WHOLE NUMBER OF 512-BYTE SD BLOCKS.  RBF's sector is 256
# bytes and the card's block is 512 (§9.4.1's deblocking), so an image with an
# odd sector count has a last block the card cannot address; the sector count
# is rounded up to even here and asserted at the end.
#
# ⛔ IT SIZES THE IMAGE TO WHAT IT IS GIVEN AND THEN CHECKS THE RESULT.  A
# short image does not announce itself: `os9 copy` onto a full disk writes
# part of a file and the machine loads a module with a bad CRC, which reads as
# a broken demo rather than a broken card.  So every file is copied back OFF
# the image and compared with the source, byte for byte, before this script
# will say ok.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)

IMG=$1
[ -n "$IMG" ] || { echo "FAIL  usage: mksddisk.sh <image> [demo ...]"; exit 1; }
shift

NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
MODS=${MODS:-$NITROS9DIR/recipes/arm6309/l2/.mods}
NAME=${NAME:-arm6309 demos}
SLACK=${SLACK:-32}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH

command -v os9 >/dev/null || {
  echo "FAIL  no os9 tool: run sh software/tools/fetch-nitros9-tools.sh"; exit 1; }
[ -d "$MODS" ] || {
  echo "FAIL  no module directory $MODS (build the ROM first: software/nitros9/mkrom.sh)"; exit 1; }

# ⭐ THE DEMO SET, and it is the recipe's $(DEMOS) list.  ⚠ If a name is added
# there it has to be added here: the two are not derived from one another, and
# a demo missing from this list is one that silently never reaches the card.
# The check below is what makes that visible - an ALL run demands every name.
ALL="rastbar wave overworld v3drag v3scrl v3grab v3trk changefont v3cpyb mvania monster pinball"
# ⚠ libvid is not a demo, it is a subroutine module, and it goes on the card
# anyway: overworld.asm F$Loads "libvid" FROM THE EXECUTION DIRECTORY when
# F$Link finds none in memory, and the execution directory is the card's CMDS
# once a bench has done `chx /sd0/cmds`.  The ROM keeps its copy too.
SUPPORT="libvid"

WANT=$*
if [ -z "$WANT" ]; then
  # every demo the build produced.  A video/ (non-V3) build has only three of
  # them, so absence is not an error here - but see the named-file check below
  WANT=""
  for d in $ALL; do [ -f "$MODS/$d" ] && WANT="$WANT $d"; done
  [ -n "$WANT" ] || { echo "FAIL  no demo modules in $MODS - did 'make demos' run?"; exit 1; }
else
  # ⛔ A NAME THAT IS NOT THERE IS A FAILURE, not an empty card.  A bench that
  # asks for `monster` off a video/ build must be told so, not handed an image
  # with nothing on it and a demo that "cannot be found" at the shell.
  for d in $WANT; do
    [ -f "$MODS/$d" ] || { echo "FAIL  no module $MODS/$d (a -DV3=1 build? 'make demos'?)"; exit 1; }
  done
fi
FILES=""
for d in $WANT $SUPPORT; do [ -f "$MODS/$d" ] && FILES="$FILES $d"; done

# ---------------------------------------------------------------------------
# ⭐ THE SIZE.  RBF: one sector for a file's descriptor plus ceil(bytes/256)
# for its data; a directory is a file too, 32 bytes an entry and two entries
# ("." and "..") before the first name; and the volume costs LSN 0, the
# allocation bitmap (one bit a sector, so ceil(N/2048) sectors) and the root.
# The bitmap depends on N and N on the bitmap, so it is solved by iterating -
# twice is enough for any card this side of a gigabyte, and the loop asserts
# the fixed point rather than assuming it.
NF=$(echo $FILES | wc -w)
DATAFILES=""
[ -n "$DATA" ] && [ -d "$DATA" ] && DATAFILES=$(ls -1 "$DATA" 2>/dev/null)
ND=$(echo $DATAFILES | wc -w)

payload=0
for f in $FILES; do
  b=$(wc -c < "$MODS/$f")
  payload=$((payload + 1 + (b + 255) / 256))
done
for f in $DATAFILES; do
  b=$(wc -c < "$DATA/$f")
  payload=$((payload + 1 + (b + 255) / 256))
done
# ⚠ A DIRECTORY IS NOT SIZED LIKE A FILE.  `os9 makdir` takes a whole
# allocation unit - eight sectors - however few entries are in it, and grows
# by eight.  Modelling a directory as ceil(entries/8) sectors made the first
# image twenty sectors short of its own slack, which is exactly the kind of
# quiet shortfall the round-trip gate at the bottom exists to catch.
dirsec() {                              # sectors for a directory of $1 entries
  s=$(( ((2 + $1) * 32 + 255) / 256 )); s=$(( (s + 7) / 8 * 8 ))
  echo $(( 1 + s ))                     # its file descriptor, then its data
}
dirs=$(( $(dirsec $NF) + $(dirsec $ND) + $(dirsec 2) ))   # CMDS, DATA, root
base=$(( 1 + dirs + payload + SLACK ))  # LSN 0, the directories, the files
N=$base
i=0
while :; do
  bm=$(( (N + 2047) / 2048 ))
  n2=$(( base + bm ))
  n2=$(( (n2 + 1) / 2 * 2 ))            # ⚠ even: 512-byte SD blocks
  [ "$n2" = "$N" ] && break
  N=$n2
  i=$((i + 1))
  [ $i -gt 8 ] && { echo "FAIL  the image size did not converge ($N sectors)"; exit 1; }
done

rm -f "$IMG"
os9 format -e -q -l$N "$IMG" -n"$NAME" || { echo "FAIL  os9 format -l$N"; exit 1; }
os9 makdir "$IMG,CMDS" || { echo "FAIL  makdir CMDS"; exit 1; }
os9 makdir "$IMG,DATA" || { echo "FAIL  makdir DATA"; exit 1; }
for f in $FILES; do
  os9 copy -o=0 "$MODS/$f" "$IMG,CMDS/$f" || { echo "FAIL  $f did not copy onto the image"; exit 1; }
done
os9 attr -q -pe -npw -pr -e -w -r $(for f in $FILES; do echo "$IMG,CMDS/$f"; done) \
  || { echo "FAIL  attr"; exit 1; }
for f in $DATAFILES; do
  os9 copy -o=0 "$DATA/$f" "$IMG,DATA/$f" || { echo "FAIL  $f did not copy into DATA"; exit 1; }
done

# ---------------------------------------------------------------------------
# ⛔ THE GATE, AND IT IS NOT OPTIONAL: `os9 copy` PRINTS "disk is filled to
# capacity" AND EXITS 0.  Found here on 2026-09-20 by shrinking the image on
# purpose - the `|| exit 1` on every copy above did not fire, `os9 attr` then
# failed on a file that was not there and exited 0 as well, and the script
# would have announced a good card carrying nothing.  So every file comes back
# OFF the image and is compared with the source, byte for byte.  A disk that
# filled up mid-copy, a name the tool truncated, an attr that did not take -
# each of them produces an image that formats, lists and boots, and a module
# the machine refuses with a CRC error twenty minutes into a bench.
VER=$(mktemp -d)
trap 'rm -rf "$VER"' EXIT
bad=0
for f in $FILES; do
  os9 copy -o=0 "$IMG,CMDS/$f" "$VER/$f" >/dev/null 2>&1 \
    || { echo "FAIL  $f cannot be read back off the image"; bad=1; continue; }
  cmp -s "$MODS/$f" "$VER/$f" \
    || { echo "FAIL  $f on the image differs from $MODS/$f ($(wc -c < "$MODS/$f") bytes in, $(cat "$VER/$f" 2>/dev/null | wc -c) out) - THE IMAGE IS SHORT"; bad=1; }
done
for f in $DATAFILES; do
  os9 copy -o=0 "$IMG,DATA/$f" "$VER/d_$f" >/dev/null 2>&1 && cmp -s "$DATA/$f" "$VER/d_$f" \
    || { echo "FAIL  DATA/$f did not survive the round trip"; bad=1; }
done
[ "$bad" -eq 0 ] || exit 1

bytes=$(wc -c < "$IMG")
[ $((bytes % 512)) -eq 0 ] || { echo "FAIL  $IMG is $bytes bytes, not a whole number of 512-byte SD blocks"; exit 1; }
[ "$bytes" -eq $((N * 256)) ] || { echo "FAIL  $IMG is $bytes bytes, not the $N sectors asked for"; exit 1; }

free=$(os9 free "$IMG" | sed -n 's/^\([0-9]*\) Free sectors.*/\1/p')
echo "ok    $IMG: $N sectors ($((bytes / 1024)) KB, $((bytes / 512)) SD blocks), ${free:-?} free"
echo "      CMDS: $FILES"
[ -n "$DATAFILES" ] && echo "      DATA: $(echo $DATAFILES)"
exit 0
