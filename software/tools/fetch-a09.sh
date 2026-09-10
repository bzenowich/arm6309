#!/bin/sh
# Fetch and build A09, the 6809/6309 assembler this project assembles with.
#
# ⚠ WHY THIS IS A SCRIPT AND NOT A VENDORED FILE — the same rule
# hardware/gal/verilog/oracle/fetch-paula.sh states, applied to a tool instead
# of a model.
#
#   A09 is (c) Hermann Seib and others, GNU GPL v2.
#   https://github.com/Arakula/A09
#
# It is a *build tool*, used the way `cc` and `verilator` are used, and its
# output carries no licence of A09's. Nothing GPL is committed to this tree and
# nothing arm6309 ships links against it. Fetching it on demand keeps that
# obvious rather than requiring an argument about it.
#
# ⭐ AND IT IS THE RIGHT TOOL RATHER THAN THE AVAILABLE ONE. It assembles the
# HD6309 instruction set as well as the 6809's, which is the CPU cpu/README.md
# says goes in the socket — so the boot ROM and the eventual NitrOS-9 work do
# not need a second assembler when the 6309's native mode is turned on.
set -e

DEST="${A09_DIR:-/tmp/arm6309-a09}"
REV="${A09_REV:-master}"
BASE="https://raw.githubusercontent.com/Arakula/A09/$REV"

mkdir -p "$DEST"

if [ ! -f "$DEST/a09.c" ]; then
  echo "fetching A09 ($REV) -> $DEST"
  curl -sSL --fail -o "$DEST/a09.c"   "$BASE/a09.c"
  curl -sSL --fail -o "$DEST/LICENSE" "$BASE/LICENSE"
  echo "fetched $(wc -c < "$DEST/a09.c") bytes"
fi

if [ ! -x "$DEST/a09" ] || [ "$DEST/a09.c" -nt "$DEST/a09" ]; then
  echo "building a09"
  # -w: it is somebody else's C and this project does not get to have opinions
  # about it. The file is byte-identical to upstream and must stay that way.
  cc -O2 -w -o "$DEST/a09" "$DEST/a09.c"
fi

"$DEST/a09" 2>&1 | head -1 >/dev/null
echo "ok    a09 is at $DEST/a09"
