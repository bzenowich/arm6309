#!/bin/sh
# Build the NitrOS-9 ROM: software/boot/boot.bin as page 0, and the port's
# recipe in $NITROS9DIR (branch arm6309) for the rest. Writes, into $1 (default
# /tmp/arm6309-nitros9):
#
#   arm6309_rom.bin   the 1 MB image
#   arm6309_rom.hex   the same bytes as $readmemh records, for mainboard.v's rom[]
#   data/             ⭐ the demo DATA, for the SD card - the Haiku desktop, Paint,
#                     the BBS, the overworld's world and the console fonts.
#                     software/nitros9/mksddisk.sh puts it in the card's DATA
#   sys/              what the caller left here before calling, copied into the
#                     ROM disk's /DD/SYS
#   romsys/           the SYSROM=... selection, likewise (SYSROM=all is the
#                     pre-2026-09-20 arrangement, for a bench with no card)
#
# Used by software/nitros9/run-emu.sh and by hardware/gal/verilog/run-machine.sh
# for +scenario=nitros9.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${1:-/tmp/arm6309-nitros9}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
export PATH="$ROOT/.tools/bin:$PATH"
mkdir -p "$OUT"

[ -n "$NITROS9DIR" ] && [ -d "$NITROS9DIR/recipes/arm6309" ] || {
  echo "FAIL  no NitrOS-9 tree with recipes/arm6309 (set NITROS9DIR; branch arm6309)"; exit 1; }
command -v lwasm >/dev/null && command -v os9 >/dev/null || {
  echo "FAIL  no lwasm/os9: run sh software/tools/fetch-nitros9-tools.sh"; exit 1; }

sh software/tools/mkrom.sh > "$OUT/mkrom.log" 2>&1 || { tail -5 "$OUT/mkrom.log"; exit 1; }
# ⭐ THE DEMO DATA GOES ON THE SD CARD, NOT IN THE ROM (2026-09-20).
#
# It used to all be copied into the ROM disk's /DD/SYS, and it is **1,140 of
# the image's 1,952 sectors** under V3=1 - 58% of the ROM disk spent on
# pictures.  The machine has storage now (storage/docs/sdcard.md 9.4), so:
#
#   $OUT/data     everything generated here.  software/nitros9/mksddisk.sh
#                 puts it in the card's DATA directory
#   $OUT/sys      what the CALLER dropped in before calling this, which is
#                 still copied into /DD/SYS.  ⚠ Not cleaned: run-v3text.sh
#                 and run-v3copyn.sh write their own streams there first
#   $OUT/romsys   the SYSROM selection, below.  Cleaned every run, because a
#                 stale copy of yesterday's SYSROM=all is a ROM disk that
#                 silently still has the data and a bench that proves nothing
#
# ⚠ SYSROM names what is ALSO kept in /DD/SYS.  `SYSROM=all` restores the old
# arrangement in one word, and the benches that boot with an EMPTY SOCKET and
# type `copy /dd/sys/...` at the shell pass it (run-vid.sh, video/run-video*.sh).
# Default is nothing: a plain build's /DD/SYS holds errmsg and no more.
DATADIR="$OUT/data"
rm -rf "$DATADIR" "$OUT/romsys"
mkdir -p "$DATADIR" "$OUT/romsys" "$OUT/sys"
# the scripted clients' byte streams (software/nitros9/tools/vtmodel.py)
python3 software/nitros9/tools/vtmodel.py --emit "$DATADIR" || { echo "FAIL  vtmodel.py --emit"; exit 1; }
python3 software/nitros9/tools/vgmodel.py --emit "$DATADIR" || { echo "FAIL  vgmodel.py --emit"; exit 1; }
# ⭐ video3's demo streams (the desktop, the draggable window, the paint
# canvas, the CP437 BBS).  Only under V3=1: they are 640 x 480 and 80 x 25
# character screens, neither of which video/ can show.
[ -n "$V3" ] && { python3 software/nitros9/tools/v3show.py "$DATADIR" || { echo "FAIL  v3show.py"; exit 1; }; }
# and the overworld's data (software/demo/tools/mkgame.py), with its model for the checker
python3 software/demo/tools/mkgame.py "$OUT/gamedata" > "$OUT/gamedata.log" || { cat "$OUT/gamedata.log"; echo "FAIL  mkgame.py"; exit 1; }
for f in tiles world sprites frames; do cp "$OUT/gamedata/$f.bin" "$DATADIR/$f.bin"; done

# ⛔ AND YESTERDAY'S SYSROM=all HAS TO GO, which cost a run to learn.  $OUT/sys
# is the CALLER's directory and is deliberately not cleaned - run-v3text.sh and
# run-v3copyn.sh write their own streams into it before calling this.  But a
# directory that was filled by an earlier `SYSROM=all` in the same $OUT then
# keeps every file, and the next build's ROM disk SILENTLY STILL HAS THE DATA:
# the bench passes, the card proves nothing, and `dir /dd/sys` is the only
# place it shows.  So every name this run generated is removed from $OUT/sys
# first, and put back only if SYSROM asks.  A name that is NOT generated here
# (the caller's own streams) is never touched.
for f in "$DATADIR"/*; do rm -f "$OUT/sys/$(basename "$f")"; done

case "${SYSROM:-}" in
  "")  ;;
  all) cp "$DATADIR"/* "$OUT/romsys/" ;;
  *)   for n in $SYSROM; do
         [ -f "$DATADIR/$n" ] || { echo "FAIL  SYSROM names $n, which nothing generated"; exit 1; }
         cp "$DATADIR/$n" "$OUT/romsys/$n"
       done ;;
esac
SYSFILES=$(ls "$OUT"/sys/* "$OUT"/romsys/* 2>/dev/null | tr '\n' ' ')
# ⛔ `grep -c` EXITS 1 WHEN THE COUNT IS ZERO, and an assignment from a failed
# command substitution kills a `set -e` script.  Counting the ROM's SYS files
# with `grep -c` therefore made an EMPTY /DD/SYS - the whole point of this
# change - abort the build with no message at all.  Count with wc.
nsys=$(( $(ls -1 "$OUT"/sys 2>/dev/null | wc -l) + $(ls -1 "$OUT"/romsys 2>/dev/null | wc -l) ))
echo "ok    the ROM disk's /DD/SYS: errmsg + $nsys file(s); the card's DATA: $(ls -1 "$DATADIR" | wc -l)"
# ⭐ the ROM toolbox's data - fonts, icons, the Haiku palette, the paint
# document - for ROM pages 65 on (tbox.asm; mktbox.py says what is where)
python3 software/nitros9/tools/mktbox.py "$OUT/tbox.bin" > "$OUT/tbox.log" || { cat "$OUT/tbox.log"; echo "FAIL  mktbox.py"; exit 1; }

# ⭐ V3=1 builds the port against video3 (video3/docs/plan.md) instead of
# video/ (graphics.md).  The difference is defs/armvid.d's register map and
# the code guarded by IFNE V3; see video3/docs/demo-report.md.
#
# ⛔ THE RECIPE HAS ONE OBJECT DIRECTORY, and changing AFLAGS does not make
# anything out of date - so switching flavour without a clean links modules
# built against the OTHER card's register offsets, which assembles, boots,
# and writes VDATA to VSTAT. The flavour is stamped and a change forces the
# clean.  (CLAUDE.md's stale-artefact trap, in a makefile.)
# ⚠ AFLAGS_MORE is folded into the stamp for the same reason: it is assembler
# flags (-DBTMARK=1, the SS.Batch instrument) that change the code without
# changing a file, so a toggle has to force the clean too.
REC="$NITROS9DIR/recipes/arm6309/l2"
FLAV=${V3:+v3}; FLAV=${FLAV:-v1}; FLAV="$FLAV${AFLAGS_MORE:+ $AFLAGS_MORE}"
if [ "$(cat "$REC/.flavour" 2>/dev/null)" != "$FLAV" ]; then
  make -C "$REC" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" clean >/dev/null 2>&1 || true
  rm -rf "$REC/.mods" "$REC/.lib"
  echo "$FLAV" > "$REC/.flavour"
fi
make -C "$REC" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" SYSFILES="$SYSFILES" TBOXDATA="$OUT/tbox.bin" \
  AFLAGS_EXTRA="${V3:+-DV3=1} $AFLAGS_MORE" \
  > "$OUT/build.log" 2>&1 || { grep -v '^lwasm\|^lwlink' "$OUT/build.log" | tail -20; echo "FAIL  the ROM did not build"; exit 1; }

cp "$NITROS9DIR/recipes/arm6309/l2/arm6309_rom.bin" "$OUT/arm6309_rom.bin"
[ "$(wc -c < "$OUT/arm6309_rom.bin")" -eq 1048576 ] || { echo "FAIL  the ROM is not 1 MB"; exit 1; }
od -An -v -tx1 -w16 "$OUT/arm6309_rom.bin" | tr -s ' ' '\n' | grep -v '^$' > "$OUT/arm6309_rom.hex"
[ "$(wc -l < "$OUT/arm6309_rom.hex")" -eq 1048576 ] || { echo "FAIL  the hex is not 1 MB of records"; exit 1; }
# page 0 must be this repository's boot ROM, byte for byte
cmp -s -n 8192 "$OUT/arm6309_rom.bin" software/boot/boot.bin || { echo "FAIL  ROM page 0 is not software/boot/boot.bin"; exit 1; }
# ⛔ AND PAGE 0 HAS A COPY OF THIS TREE'S OFFSETS IN IT.  boot.asm 10a draws the
# boot dialog with the ROM toolbox and therefore reads CoArm's globals, and A09
# cannot include defs/armvid.d.  checkcg.py re-derives all 22 with lwasm and
# says so; without it a field that moved here would move the dialog's clip and
# nothing would notice (software/nitros9/tools/checkcg.py says the rest).
python3 software/nitros9/tools/checkcg.py "$NITROS9DIR" || exit 1
echo "ok    $OUT/arm6309_rom.bin and .hex, page 0 = software/boot/boot.bin"
