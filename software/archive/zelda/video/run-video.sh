#!/bin/sh
# run-video.sh - the Zelda-like overworld, as a room game, as a demo video.
#
#   make -C software/zelda video     the H.264 file -> video/zelda-demo.mp4
#   make -C software/zelda sheet     a contact sheet of the same run -> build/video/sheet.png
#
# `zelda 0 2500 8` - 2,500 frames, the hero and eight creatures, rooms sliding in.
# It reproduces build/run/zvid/zelda-demo.mp4 (2026-09-23).
#
# ⭐ IT RUNS THE PROGRAM.  software/tools/video/record.sh boots NitrOS-9 off the
# system card on the host emulator, types the command below at the shell and
# keeps every frame; clip.py cuts the scene out and encodes it (2x, 30 fps,
# x264 crf 20).  REVIEW THE SHEET FIRST: it takes seconds, the video minutes.
#
#   KEEP=1   keep the recording (build/video/frames.bin, several hundred MB)
#   NORUN=1  re-encode the recording that is already there
#   MP4=...  write the video somewhere else
# ⚠ Needs ../nitros9 on its arm6309 branch, like every software bench.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
H=$(cd "$_here/.." && pwd)
R=$(cd "$H/../.." && pwd)
V="$R/software/tools/video"
OUT=${OUT:-$H/build/video}
MP4=${MP4:-$_here/zelda-demo.mp4}
if [ -z "$NORUN" ]; then
  LINES='iniz w5\rchx /sd0/cmds\rzelda 0 2500 8 >/w5\recho DONE-arm6309\r' SECS=200 \
    sh "$V/record.sh" "$OUT"
fi
if [ -n "$SHEET" ]; then
  python3 "$V/clip.py" "$OUT" "$MP4" --scene "zelda 0 2500 8" --keep --sheet "$OUT/sheet.png"
else
  python3 "$V/clip.py" "$OUT" "$MP4" --scene "zelda 0 2500 8" ${KEEP:+--keep}
fi
