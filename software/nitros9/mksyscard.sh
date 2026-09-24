#!/bin/sh
# ⭐ A BOOTABLE SYSTEM CARD: NitrOS-9 itself, plus whatever demos are asked for.
#
#   sh software/nitros9/mksyscard.sh /tmp/x/sd.img [demo ...]
#   DATA=dir     the card's DATA directory (default $OUT/data)
#   OUT=dir      where mkrom.sh put its build (default /tmp/arm6309-nitros9)
#   NAME="..."   the volume name
#
# ⛔ SINCE 2026-09-22 THE ROM CARRIES NO FILESYSTEM, so a card that is not
# BOOTABLE is a machine that does not start.  Every bench that used to build a
# plain data card with mksddisk.sh needs this instead - and a bench that wants
# a DELIBERATELY unbootable card (run-sdboot.sh's `plain`) still calls
# mksddisk.sh directly, which is the whole difference between them.
#
# The command set and the /MODULES list come from the port's own recipe
# (`make print-syscard`, `print-modules`), so a card cannot drift from the
# NitrOS-9 that is built beside it.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
IMG=$1; shift || true
[ -n "$IMG" ] || { echo "FAIL  usage: mksyscard.sh IMG [demo ...]"; exit 1; }
OUT=${OUT:-$(cd "$_here/." && pwd)/build/rom}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
export PATH="$ROOT/.tools/bin:$PATH"

[ -f "$REC/bootfile" ] || { echo "FAIL  no $REC/bootfile - run mkrom.sh first"; exit 1; }

# ⛔ MAKE expands these, not a sed over the makefile: SYSCARD is `$(CMDS)` and
# the `+=` lines after its definition are invisible to anything but make.
SYSC=$(make -s -C "$REC" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" print-syscard 2>/dev/null)
MODL=$(make -s -C "$REC" NITROS9DIR="$NITROS9DIR" ARM6309DIR="$ROOT" print-modules 2>/dev/null)
[ -n "$SYSC" ] || { echo "FAIL  the recipe printed no SYSCARD list"; exit 1; }

W="$OUT/.syscard"
rm -rf "$W"; mkdir -p "$W/sys" "$W/mods"
cp "$NITROS9DIR/level1/sys/errmsg" "$W/sys/errmsg"
# ⭐ AND /SYS IS WHERE $OUT/sys AND $OUT/romsys LAND, which is what keeps
# `copy /dd/sys/...` working now that there is no ROM disk to hold them.
# mkrom.sh owns both directories: `sys` is what the CALLER dropped there
# (run-v3text.sh and run-v3copyn.sh write their own byte streams into it),
# `romsys` is the SYSROM= selection.  ⚠ A bench that reads /dd/sys is reading
# the CARD now; an empty socket is an empty /SYS.
for d in "$OUT/sys" "$OUT/romsys"; do
  [ -d "$d" ] && { for f in "$d"/*; do [ -f "$f" ] && cp "$f" "$W/sys/"; done; }
done
true
# ⚠ /MODULES CARRIES MERGED FILES NAMED FOR THE MODULE, not the raw .dr and
# .dd: `load /dd/modules/firqtst` names a FILE, and a card carrying
# firqtst.dr and ft0.dd answers Error #216.
for m in $MODL; do
  [ -f "$REC/modules_$m" ] || { echo "FAIL  no $REC/modules_$m"; exit 1; }
  cp "$REC/modules_$m" "$W/mods/$m"
done
# ⚠ /DD IS THE CARD now, so this is where the shell starts looking.
printf 'chx /dd/cmds\r' > "$W/startup"

# ⭐ BOOT= IS OVERRIDABLE, and `BOOT=` (set and EMPTY) is how a bench asks for
# a card that carries the whole system and is deliberately NOT bootable -
# run-sdboot.sh's `plain` control, which has to be a card the machine can READ
# and must not boot from.  ⚠ `${BOOT-...}`, not `${BOOT:-...}`: the second
# would silently substitute the default for exactly that case.
SYSCMDS="$SYSC" SYSMODDIR="$W/mods" SYSDIR="$W/sys" STARTUP="$W/startup" \
  BOOT="${BOOT-$REC/bootfile}" NAME="${NAME:-arm6309 system}" MODS="$REC/.mods" \
  DATA="${DATA:-$OUT/data}" \
  sh software/nitros9/mksddisk.sh "$IMG" "$@"
