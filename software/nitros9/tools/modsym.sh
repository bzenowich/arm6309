#!/bin/sh
# modsym.sh OUT SOURCE SYMBOL - the offset, in hex, of SYMBOL in the module
# assembled from SOURCE (a .asm under $NITROS9DIR), by re-running the exact
# lwasm command the recipe used (from OUT/build.log, written by mkrom.sh) with a
# listing. For the emulator's CALLTIME, which names a routine as Module+$off.
set -e
OUT=$1; SRC=$2; SYM=$3
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" && pwd)}
export PATH="$ROOT/.tools/bin:$PATH"
# the recipe's own command for the module, whether or not it was rebuilt: make -n -W
cmd=$(cd "$NITROS9DIR/recipes/arm6309/l2" && make -n -W "$NITROS9DIR/level2/arm6309/modules/$SRC" NITROS9DIR="$NITROS9DIR" all 2>/dev/null | grep "^lwasm .*/$SRC " | head -1)
[ -n "$cmd" ] || { echo "modsym: make -n gives no lwasm line for $SRC" >&2; exit 1; }
cmd=$(echo "$cmd" | sed "s| -o[^ ]*| -o$OUT/modsym.bin -l$OUT/modsym.lst|")
(cd "$NITROS9DIR/recipes/arm6309/l2" && eval "$cmd") >/dev/null 2>&1
awk -v s="$SYM" '$0 ~ "\\):[0-9]+ +"s"( |$)" && $1 ~ /^[0-9A-F][0-9A-F][0-9A-F][0-9A-F]$/ {print $1; exit}' "$OUT/modsym.lst"
