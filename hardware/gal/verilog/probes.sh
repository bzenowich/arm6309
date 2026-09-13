#!/bin/sh
# Ensure the single-effect probe corpus exists, and print the directory holding it.
#
#   sh gal/verilog/probes.sh          (from hardware/)   -> prints the directory
#
# ⛔ WHY THIS EXISTS. `npm run check:modplay` used to name
# /tmp/arm6309-mod/00_notes.mod directly, and nothing created it. The corpus is
# SYNTHESISED - audio/tools/modcompare/mkprobe.py writes its own saw and square
# samples and needs no download - so the check was never waiting on an asset,
# only on a scratch path that does not survive a reboot. The failure mode is the
# one CLAUDE.md's trap list is about: the repository's strongest audio check
# (audio.md §16 items 40, 41, 43 and 44 all came out of it) stops being runnable
# and says so only when somebody runs it.
#
# $ARM6309_MOD overrides the location, for a corpus kept somewhere durable.
set -e
cd "$(dirname "$0")"
ROOT=$(cd ../../.. && pwd)

DIR=${ARM6309_MOD:-/tmp/arm6309-mod}

# Regenerate only when the probe check:modplay plays is absent. mkprobe.py
# creates the directory itself (os.makedirs(exist_ok=True)) and is deterministic,
# so a partial corpus is repaired by the same command.
if [ ! -f "$DIR/14_fourchan.mod" ]; then
  echo "-- regenerating the probe corpus in $DIR" >&2
  python3 "$ROOT/audio/tools/modcompare/mkprobe.py" "$DIR" >&2
fi

echo "$DIR"
