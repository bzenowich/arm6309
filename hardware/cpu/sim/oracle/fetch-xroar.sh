#!/bin/sh
# fetch-xroar.sh - build the 6309 ORACLE: XRoar's HD6309 core, run by our harness.
#
#   sh hardware/cpu/sim/oracle/fetch-xroar.sh      -> hardware/cpu/build/oracle/xroar_run
#
# ⭐ WHY XRoar.  hardware/cpu/docs/6309.md §4.2: a model with nothing to be
# checked against is an assertion nobody has checked.  XRoar (Ciaran Anscomb,
# a Dragon/CoCo emulator) has a mature, cycle-counted HD6309 in plain C, and
# its core needs a dozen stub symbols to run on its own.
#
# ⛔ IT IS NEVER COPIED INTO THIS REPOSITORY.  XRoar is GPL-3.0; the files are
# FETCHED, at one pinned commit, into build/ and compiled with our harness into
# a separate executable that writes a trace.  That is §4.2's rule for an oracle
# ("a separate executable producing a trace to diff against, never source
# merged into ours").  The mirror is stahta01/xroar on GitHub, because
# www.6809.org.uk is not reachable from where this is developed.
#
# EXIT CODE IS THE ANSWER.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
SHA=0c3ddf17ee899ecd385a5912e212b14975d19657
RAW=https://raw.githubusercontent.com/stahta01/xroar/$SHA
O=$ROOT/hardware/cpu/build/oracle
X=$O/xroar
mkdir -p "$X/mc680x"
FILES="src/mc6809/hd6309.c src/mc6809/hd6309.h src/mc6809/mc6809.h src/mc6809/mc6809_common.c
src/mc680x/mc680x_ops.c src/part.h src/logging.h src/serialise.h src/debug.h
portalib/array.h portalib/delegate.h portalib/intfuncs.h portalib/pl-endian.h
portalib/xalloc.h portalib/sds.h top-config.h COPYING.GPL"
for f in $FILES; do
  b=$(basename "$f")
  case "$f" in src/mc680x/*) d="$X/mc680x/$b" ;; *) d="$X/$b" ;; esac
  [ -s "$d" ] && continue
  curl -sfL -o "$d" "$RAW/$f" || { echo "FAIL  fetch-xroar: cannot fetch $f at $SHA"; exit 1; }
done
echo "ok    XRoar's HD6309 at $SHA, $(wc -l < "$X/hd6309.c") lines, in $X"
cc -std=gnu11 -O2 -w -I"$X" -I"$HERE" -o "$O/xroar_run" \
   "$HERE/xroar_run.c" "$HERE/xroar_stubs.c" ||
  { echo "FAIL  fetch-xroar: the oracle does not build"; exit 1; }
echo "ok    $O/xroar_run"
