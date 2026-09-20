#!/bin/sh
# Build the NitrOS-9 ROM: software/boot/boot.bin as page 0, and the port's
# recipe in $NITROS9DIR (branch arm6309) for the rest. Writes, into $1 (default
# /tmp/arm6309-nitros9):
#
#   arm6309_rom.bin   the 1 MB image
#   arm6309_rom.hex   the same bytes as $readmemh records, for mainboard.v's rom[]
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
# the scripted clients' byte streams, into /DD/SYS (software/nitros9/tools/vtmodel.py)
python3 software/nitros9/tools/vtmodel.py --emit "$OUT/sys" || { echo "FAIL  vtmodel.py --emit"; exit 1; }
python3 software/nitros9/tools/vgmodel.py --emit "$OUT/sys" || { echo "FAIL  vgmodel.py --emit"; exit 1; }
# ⭐ video3's demo streams (the desktop, the draggable window, the paint
# canvas, the CP437 BBS).  Only under V3=1: they are 640 x 480 and 80 x 25
# character screens, neither of which video/ can show.
[ -n "$V3" ] && { python3 software/nitros9/tools/v3show.py "$OUT/sys" || { echo "FAIL  v3show.py"; exit 1; }; }
# and the overworld's data (software/demo/tools/mkgame.py), with its model for the checker
python3 software/demo/tools/mkgame.py "$OUT/gamedata" > "$OUT/gamedata.log" || { cat "$OUT/gamedata.log"; echo "FAIL  mkgame.py"; exit 1; }
for f in tiles world sprites frames; do cp "$OUT/gamedata/$f.bin" "$OUT/sys/$f.bin"; done
SYSFILES=$(ls "$OUT"/sys/* | tr '\n' ' ')
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
echo "ok    $OUT/arm6309_rom.bin and .hex, page 0 = software/boot/boot.bin"
