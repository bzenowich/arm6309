#!/bin/sh
# Fetch Paula.v for the differential oracle.
#
# ⚠ WHY THIS IS A SCRIPT AND NOT A VENDORED FILE.
#
# The oracle compares this card against an INDEPENDENT implementation of
# Paula - that independence is the whole point, because audio_tb.sv was
# written from the same understanding that produced the design and can only
# confirm the design does what its author thought. On 2026-09-10 the oracle
# found two live defects (audio.md 16 item 36) that 483 checks, a design
# review and a port census had all missed.
#
# ⛔ BUT ITS LICENSING IS UNSETTLED AND WE DO NOT VENDOR IT.
#
#   Paula.v's own header  : GNU GPL v3
#   the repository's file : Creative Commons Attribution-NonCommercial 4.0
#
# Those are incompatible, and NC is a real restriction on a hardware project
# that might one day be sold. Rather than import that ambiguity into this
# tree, the oracle fetches it on demand. Nothing GPL- or CC-licensed is
# committed here, and no obligation attaches to arm6309.
#
# ⚠ AND THE TWO MODELS ARE NEVER LINKED. run-oracle.sh builds two SEPARATE
# binaries and compares their output. That is cleaner legally than one mixed
# netlist, and it is better testing - neither model can contaminate the other.
set -e

DEST="${1:-/tmp/arm6309-oracle}"
URL="https://raw.githubusercontent.com/nonarkitten/amiga_replacement_project/master/paula/Paula.v"

mkdir -p "$DEST"

if [ -f "$DEST/Paula.v" ]; then
  echo "already present: $DEST/Paula.v"
else
  echo "fetching Paula.v -> $DEST"
  curl -sSL --fail -o "$DEST/Paula.v" "$URL"
  echo "fetched $(wc -c < "$DEST/Paula.v") bytes"
fi

# It is the upstream author's work under the upstream author's terms. Read
# them before doing anything with it beyond running the oracle locally.
cat <<'NOTE'

  Paula.v is (c) Renee Cousins and Frederic Requin, Amiga Replacement Project.
  Its file header states GNU GPL v3; the project's LICENSE.md states CC BY-NC
  4.0. Read both before redistributing, modifying, or using it commercially.
  It is fetched here ONLY as a local test oracle and is not part of arm6309.

NOTE

verilator --lint-only -Wno-lint "$DEST/Paula.v" \
  && echo "ok  Paula.v parses under this Verilator"
