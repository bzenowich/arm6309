#!/bin/sh
# Fetch an ffmpeg with libx264, for software/demo/tools/mkvideo.py.
#
# The imageio-ffmpeg wheel on PyPI carries a static ffmpeg built with libx264
# and AAC. It is fetched and unpacked here rather than pip-installed, because
# the system Python is externally managed (PEP 668), and it is NOT vendored -
# ffmpeg is GPL and a build tool, the same rule fetch-a09.sh states.
#
# Prints the path of the executable.
set -e
DEST="${FFMPEG_DIR:-/tmp/arm6309-ffmpeg}"
if [ ! -x "$DEST/ffmpeg" ]; then
  mkdir -p "$DEST"
  pip download imageio-ffmpeg --no-deps --only-binary=:all: -d "$DEST/wheel" > /dev/null
  python3 -m zipfile -e "$DEST"/wheel/imageio_ffmpeg-*.whl "$DEST/unpacked"
  cp "$DEST"/unpacked/imageio_ffmpeg/binaries/ffmpeg-* "$DEST/ffmpeg"
  chmod +x "$DEST/ffmpeg"
fi
"$DEST/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -q libx264 \
  || { echo "FAIL  $DEST/ffmpeg has no libx264" >&2; exit 1; }
echo "$DEST/ffmpeg"
