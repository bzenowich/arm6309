#!/bin/sh
# run-video.sh - the metroidvania scene: a contact sheet, or a video.
#
#   make -C software/mvania sheet    record the run, and a contact sheet of it
#                                  -> build/video/sheet.png            ~2 min
#   make -C software/mvania video    the H.264 file OF THAT SAME RUN -> video/mvania-demo.mp4
#
# `mvania 0 45 1393` - mode 0, a step every 45 frames, the bench's fixed cost.
#
# ⭐ SHEET FIRST, ALWAYS.  A demo is reviewed from its contact sheet and the
# video is made only once the sheet is approved - so `sheet` keeps the
# recording, and `video` encodes exactly the run the sheet was made from
# rather than recording a different one.  With no sheet (or FRESH=1) `video`
# records first.
#
#   FRESH=1  record again even though there is a reviewed run
#   KEEP=1   keep the recording after the video (build/video/frames.bin)
#   MP4=...  write the video somewhere else
#
# ⭐ IT RUNS THE PROGRAM: software/tools/video/record.sh boots NitrOS-9 off the
# system card on the host emulator and types the command below; clip.py cuts
# the scene out by the serial log and encodes it (2x, 30 fps, x264 crf 20).
# ⚠ Needs ../nitros9 on its arm6309 branch, like every software bench.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/video}
MP4=${MP4:-$_here/mvania-demo.mp4}
CLIP="--scene \"mvania 0 45 1393\" --max 40"
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='chx /sd0/cmds\riniz w5\rmvania 0 45 1393 >/w5\recho DONE-arm6309\r' SECS=150 \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/video/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 12 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: make -C software/mvania video"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
