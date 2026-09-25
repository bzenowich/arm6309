#!/bin/sh
# run-build.sh - a table built from nothing at the editor, then played: a
# contact sheet, or a video.
#
#   SHEET=1 sh software/pcs/video/run-build.sh   record, and a contact sheet
#                                                  -> build/build/sheet.png    ~4 min
#   sh software/pcs/video/run-build.sh           the H.264 file OF THAT SAME RUN
#                                                  -> video/pcs-build.mp4
#
# `pcs 24` - the editor on a NEW table, the backdrop alone - driven by
# bench/scripts/pcsbuild.ps2 (mkpcsbuild.py writes it): the parts out of the bin,
# each one a live drag; a polygon stretched into the chute's divider with the
# pointer; paint; PLAY with the flippers; a bumper moved; PLAY again.  The
# Apple II session in reference/pcs-apple2-editor.mp4 is what it follows.
#
# ⭐ SHEET FIRST, as run-video.sh: `SHEET=1` keeps the recording, and the video
# is encoded from exactly the run the sheet was made from.  FRESH=1 records again.
_here=$(cd "$(dirname "$0")" && pwd)
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/build}
MP4=${MP4:-$_here/pcs-build.mp4}
CLIP="--scene \"pcs 24 20000\""
python3 "$H/bench/scripts/mkpcsbuild.py" > "$H/bench/scripts/pcsbuild.ps2"
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='chx /sd0/cmds\riniz w5\rpcs 24 20000 >/w5\recho DONE-arm6309\r' SECS=300 \
    PS2FILE="$H/bench/scripts/pcsbuild.ps2" PS2_GATE=PCS-EDIT \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/build/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 24 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: sh software/pcs/video/run-build.sh"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
