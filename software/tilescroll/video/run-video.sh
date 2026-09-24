#!/bin/sh
# run-video.sh - Explore (`tilescroll`): the camera roaming a 4096 x 2048 world, with creatures: a contact sheet, or a video.
#
#   make -C software/tilescroll sheet    record the run, and a contact sheet of it
#                                  -> build/video/sheet.png            ~3 min
#   make -C software/tilescroll video    the H.264 file OF THAT SAME RUN -> video/${NAME}.mp4
#
# `tilescroll 0 1200 $ACTORS` - 1,200 frames of the camera walking its eight-leg path with
# ACTORS creatures (default 5 -> tilescroll-actors.mp4; ACTORS=0 is the engine alone ->
# tilescroll-demo.mp4).  The clip of 2026-09-23 was made from this command.
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
ACTORS=${ACTORS:-5}
NAME=tilescroll-actors; [ "$ACTORS" -gt 0 ] || NAME=tilescroll-demo
OUT=${OUT:-$H/build/video}
MP4=${MP4:-$_here/${NAME}.mp4}
CLIP="--scene \"tilescroll 0 1200 $ACTORS\""
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES="chx /sd0/cmds\\riniz w5\\rtilescroll 0 1200 $ACTORS >/w5\\recho DONE-arm6309\\r" SECS=150 \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/video/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 12 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: make -C software/tilescroll video"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
