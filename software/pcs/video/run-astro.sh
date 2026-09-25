#!/bin/sh
# run-astro.sh - pcs from the desktop, Astro Blast recoloured and played: a
# contact sheet, or a video.
#
#   SHEET=1 sh software/pcs/video/run-astro.sh   record, and a contact sheet
#                                                  -> build/astro/sheet.png    ~5 min
#   sh software/pcs/video/run-astro.sh           the H.264 file OF THAT SAME RUN
#                                                  -> video/pcs-astro.mp4
#
# `desk`, and bench/scripts/pcsastro.ps2 (mkpcsastro.py writes it) driving it:
# the Pinball icon opened, Astro Blast LOADed off the card through DISK, both
# flippers painted light blue, a round bumper out of the bin painted yellow,
# GRAVITY set to 5 on the WORLD panel, fifteen seconds of PLAY, and `q` back
# to the desktop.
#
# ⭐ SHEET FIRST, as run-video.sh: `SHEET=1` keeps the recording, and the video
# is encoded from exactly the run the sheet was made from.  FRESH=1 records again.
_here=$(cd "$(dirname "$0")" && pwd)
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/astro}
MP4=${MP4:-$_here/pcs-astro.mp4}
CLIP="--scene \"desk /w3 60000\""
python3 "$H/bench/scripts/mkpcsastro.py" > "$H/bench/scripts/pcsastro.ps2"
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='iniz w3\rchd /sd0\rchx /sd0/cmds\rdesk /w3 60000\recho DONE-arm6309\r' SECS=260 \
    PS2FILE="$H/bench/scripts/pcsastro.ps2" PS2_GATE=DESK-READY \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/astro/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 30 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: sh software/pcs/video/run-astro.sh"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
