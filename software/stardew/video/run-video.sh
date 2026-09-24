#!/bin/sh
# run-video.sh - the farm, and the day passing in the palette: a contact sheet, or a video.
#
#   make -C software/stardew sheet    record the run, and a contact sheet of it
#                                  -> build/video/sheet.png            ~3 min
#   make -C software/stardew video    the H.264 file OF THAT SAME RUN -> video/stardew-demo.mp4
#
# `stardew 0 1050 7` - mode 0, 1,050 frames, seven actors: the run bench/run-v3star.sh's
# m0 leg makes the committed sheets (bench/stardew-sheets/) from.  The sheet has 18
# tiles, as those do.  ⚠ The farm's 480 KB picture is not on the general system
# card, so this run builds a card of its own with it, as that bench does.
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
MP4=${MP4:-$_here/stardew-demo.mp4}
CLIP="--scene \"stardew 0 1050 7\" --hold 1.5"
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='chx /sd0/cmds\riniz w5\rstardew 0 1050 7 >/w5\recho DONE-arm6309\r' SECS=95 \
    CARD_DATA="$H/bench/stardew.pic" CARD_DEMOS=stardew \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/video/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 18 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: make -C software/stardew video"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
