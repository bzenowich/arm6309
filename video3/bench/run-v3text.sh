#!/bin/sh
# What a ROM toolbox text call costs, on NitrOS-9, measured.
#
#   sh video3/bench/run-v3text.sh          OUT=dir overrides
#
# ⭐ THE FIRST MEASUREMENT OF THE TOOLBOX IN THIS REPOSITORY.  Everything about
# tbox.asm's speed was arithmetic until this: video3/bench/README.md's "⛔ Does
# not answer - timing", demo-report.md §13, and §14.4 on why CALLTIME cannot
# reach CoArm.  mkv3text.py says how it is done and why every stream is timed
# twice.
#
# ⚠ It boots NitrOS-9, unlike the other benches here: the toolbox is reached
# through CoArm's ESC $6A, so there is no bare-metal way to call it.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3text}
rm -rf "$OUT"; mkdir -p "$OUT/sys"

# the bench's streams first: mkrom.sh adds v3show.py's to the same directory
# and then takes the lot as SYSFILES
python3 video3/bench/mkv3text.py "$OUT/sys" > "$OUT/mk.log" || { cat "$OUT/mk.log"; exit 1; }
V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

# ⚠ CR, NOT LF.  A \n-terminated typed.txt is echoed by the shell and run by
# nothing, which reads exactly like a hung machine (demo-report.md §14.3).
python3 - "$OUT" <<'PY'
import sys
sys.path.insert(0, "video3/bench")
import mkv3text as M
lines = ["iniz w5", "copy /dd/sys/v3tset /w5"]
for n in M.TIMED:                      # /nil first: the stream's own cost
    lines += ["copy /dd/sys/%s /nil" % n, "copy /dd/sys/%s /w5" % n]
# ⚠ v3tcache runs FIRST of the two, then v3tcmp, then a marker copy: if the
# session wedges, whether the LATER commands ran says whether the console
# survived the call or the copy itself never returned.  Both bands survive to
# the dump either way - nothing after this draws in them.
lines += ["copy /dd/sys/v3tcache /w5", "copy /dd/sys/v3tstrk /w5",
          "copy /dd/sys/v3tcmp /w5", "echo CACHE-PAST"]
lines += ["echo DONE-arm6309"]
open(sys.argv[1] + "/typed.txt", "w").write("\r".join(lines) + "\r")
PY

STOP=$(printf '\nDONE-arm6309')
(cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
   SERIAL_TIMES=serial.times SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 VRAMDUMP=vram.bin \
   ./emu arm6309_rom.bin . 600 > /dev/null 2> emu.log) || true
grep -q "SERIAL_STOP seen" "$OUT/emu.log" || { tail -3 "$OUT/emu.log"; echo "FAIL  the session did not finish"; exit 1; }
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
if grep -n "Error #" "$OUT/console.txt"; then echo "FAIL  a command failed"; exit 1; fi

python3 video3/bench/checkv3text.py "$OUT"
