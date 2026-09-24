#!/bin/sh
# run-video.sh - Pinball Construction Set, played: a contact sheet, or a video.
#
#   make -C software/pcs sheet    record the run, and a contact sheet of it
#                                  -> build/video/sheet.png            ~3 min
#   make -C software/pcs video    the H.264 file OF THAT SAME RUN -> video/pcs-play.mp4
#
# `pcs 20 1500 demo2.pbt` - mode 20, PLAY IT: the mouse is the joystick, driven by
# bench/scripts/pcsplay.ps2 (a launch and the flippers), on the first shipped table.
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
# ⚠ The table comes off the retail disk image in reference/ (docs/pcs.md 5c); without it
# mkrom.sh puts no tables on the card and `pcs` refuses the name.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/video}
MP4=${MP4:-$_here/pcs-play.mp4}
CLIP="--scene \"pcs 20 1500 demo2.pbt\""
if [ -n "$SHEET" ] || [ -n "$FRESH" ] || [ ! -f "$OUT/frames.bin" ] || [ ! -f "$OUT/sheet.png" ]; then
  LINES='chx /sd0/cmds\riniz w5\rpcs 20 1500 demo2.pbt >/w5\recho DONE-arm6309\r' SECS=120 \
    PS2FILE="$R/software/pcs/bench/scripts/pcsplay.ps2" PS2_GATE=PCS-PLAY \
    sh "$V/record.sh" "$OUT"
else
  echo "      encoding the run build/video/sheet.png was made from (FRESH=1 records again)"
fi
if [ -n "$SHEET" ]; then
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP --keep --tiles 12 --sheet "\"$OUT/sheet.png\""
  echo "      review it; then: make -C software/pcs video"
else
  eval python3 "\"$V/clip.py\"" "\"$OUT\"" "\"$MP4\"" $CLIP ${KEEP:+--keep}
fi
