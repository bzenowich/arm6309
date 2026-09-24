#!/bin/sh
# run-video.sh - Paint, the BBS or the ANSI art - WHICH=v3paint, v3bbs or v3art: a contact sheet, or a video.
#
#   make -C software/paint sheet WHICH=v3bbs    record the run, and a contact sheet of it
#                                  -> build/video/$WHICH/sheet.png            ~2 min
#   make -C software/paint video WHICH=v3bbs    the H.264 file OF THAT SAME RUN -> video/$WHICH.mp4
#
# `$WHICH 600` - the recorded CoArm stream, shown by the program the desktop forks and
# held for 600 ticks (~10 s).  v3bbs is the BBS in 80 x 25; v3art is Blocktronics'
# we-tortuga (only if reference/we-tortuga.ans is here); v3paint is the painted page.
# `make sheet` / `make video` with no WHICH do all three.
#
# ⭐ SHEET FIRST, ALWAYS.  A demo is reviewed from its contact sheet and the
# video is made only once the sheet is approved - so `sheet` keeps the
# recording, and `video` encodes exactly the run the sheet was made from
# rather than recording a different one.  With no sheet (or FRESH=1) `video`
# records first.
#
#   FRESH=1  record again even though there is a reviewed run
#   KEEP=1   keep the recording after the video (build/video/$WHICH/frames.bin)
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
WHICH=${WHICH:-v3bbs}
case $WHICH in v3bbs|v3art|v3paint) ;; *) echo "FAIL  WHICH is v3bbs, v3art or v3paint"; exit 1 ;; esac
OUT=${OUT:-$H/build/video/$WHICH}
MP4=${MP4:-$_here/$WHICH.mp4}
CLIP="--scene \"$WHICH 600\""
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES="iniz w5\\rchd /sd0\\rchx /sd0/cmds\\r$WHICH 600 >/w5\\recho DONE-arm6309\\r" SECS=90 \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/video/$WHICH/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 12 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: make -C software/paint video WHICH=v3bbs"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
