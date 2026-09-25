#!/bin/sh
# run-magnify.sh - the magnifier at the editor, on the demo table: a
# contact sheet, or a video.
#
#   SHEET=1 sh software/pcs/video/run-magnify.sh   record, and a contact sheet
#                                                  -> build/magnify/sheet.png    ~4 min
#   sh software/pcs/video/run-magnify.sh           the H.264 file OF THAT SAME RUN
#                                                  -> video/pcs-magnify.mp4
#
# `pcs 23` - the editor on the demo table - driven by bench/scripts/pcsmag.ps2,
# the script run-pcs.sh's `e2` leg gates: MAGN, lines of fat bits drawn and one
# erased by the brush's toggle, the box moved across the table, QUIT, MAGN again
# in another colour, a tool that ends it, and a last line with it left up.
#
# ⭐ SHEET FIRST, as run-video.sh: `SHEET=1` keeps the recording, and the video
# is encoded from exactly the run the sheet was made from.  FRESH=1 records again.
_here=$(cd "$(dirname "$0")" && pwd)
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/magnify}
MP4=${MP4:-$_here/pcs-magnify.mp4}
CLIP="--scene \"pcs 23 9000\""
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='chx /sd0/cmds\riniz w5\rpcs 23 9000 >/w5\recho DONE-arm6309\r' SECS=200 \
    PS2FILE="$H/bench/scripts/pcsmag.ps2" PS2_GATE=PCS-EDIT \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/magnify/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 24 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: sh software/pcs/video/run-magnify.sh"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
