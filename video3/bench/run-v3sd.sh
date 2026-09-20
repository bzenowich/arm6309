#!/bin/sh
# ⭐ A DEMO THAT IS NOT IN THE ROM, RUN OFF THE SD CARD.
#
#   sh video3/bench/run-v3sd.sh          ~1 min (4 with a clean ROM build).
#                                        OUT=dir, DEMO=name, DEMOARGS=..., NOBUILD=1
#
# Until 2026-09-20 every demo program was inside the boot ROM's 488 K RBF
# image, the image was FULL, and a scene had to ask the recipe for its command
# and give back the room (CMDS_EXTRA / CMDS_DROP).  The machine now has
# storage - an SD card at $FF58, the rbsd driver, /SD0 (storage/docs/
# sdcard.md §9.4) - so the applications moved off the ROM and onto a card,
# and the ROM disk is a rescue system: the kernel, the shell, the shared
# modules and enough commands to format a card and fill it.
#
# ⭐ THIS BENCH IS ABOUT WHERE THE PROGRAM CAME FROM, not about the scene.  It
# runs a few frames and no more; run-v3mv.sh is what measures the scene.  The
# four things it has to establish are:
#
#   1. the machine boots and /SD0 mounts - the host's os9 tools wrote the
#      image and NitrOS-9's RBF reads it, two implementations agreeing
#   2. ⭐ the demo LOADED AND RAN.  Not that the command was typed: that a
#      moving, many-coloured picture reached the card's output, which is
#      checkv3sd.py's `painted` and `changed` counts and which nothing but a
#      program that loaded and ran can produce
#   3. the ROM disk does NOT carry that demo - asked of the machine
#      (`dir /dd/cmds`) and of the image on the host, because if it were
#      still in the ROM the run above would prove nothing at all
#   4. ⛔ THE NEGATIVE CONTROL: the same ROM, the same keystrokes, and NO
#      CARD IN THE SOCKET.  /SD0 must refuse at 9.0, the demo must not be
#      found, no picture may be painted - and the run must REACH THE END
#      rather than hang, because a bench that hangs on a missing card is a
#      bench that cannot tell a missing card from a slow one.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3sd}
DEMO=${DEMO:-mvania}
# mvania's arguments: mode 0 (the scene as designed), two frames a step - its
# sweep is fourteen steps, so this is 28 frames of scene, which is all this
# bench wants - and SS.CopyN's 1,393-byte fixed cost (run-v3mv.sh §).
DEMOARGS=${DEMOARGS:-"0 2 1393"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-120}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD, MADE BY THE TOOLCHAIN.  One demo and nothing else: the image is
# sized to what it is given, so this is ~30 KB rather than the 100 KB a full
# demo card is, and a short one would fail loudly there rather than quietly
# here (software/nitros9/mksddisk.sh).
sh software/nitros9/mksddisk.sh "$OUT/sd.img" "$DEMO" > "$OUT/mksddisk.log" 2>&1 || {
  cat "$OUT/mksddisk.log"; echo "FAIL  the demo card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

# ⚠ CR, not LF (demo-report.md §15.3), and `dir` BEFORE `chx`: after the
# execution directory moves to the card, the only commands that can be forked
# are the card's own and shell+'s merged built-ins (echo, iniz, load, link) -
# which is itself part of the point.
printf 'dir /sd0\rdir /sd0/cmds\rdir /dd/cmds\rchd /sd0\rchx /sd0/cmds\riniz w5\r%s %s >/w5\recho DONE-arm6309\r' \
  "$DEMO" "$DEMOARGS" > "$OUT/typed.txt"

# ⚠ THE GATE IS "02}", NOT "DD:".  Every other video bench waits for the
# ROM disk's prompt - and `chd /sd0` changes the prompt to /SD0:, so a bench
# that waited for "DD:" would stall on its own third line for the whole
# SECONDS_OF_MACHINE and report "did not finish".  `{Term|02}` is in the
# prompt whatever the data directory is.
STOP=$(printf '\nDONE-arm6309')
run() {   # run DIR  [extra env assignments are taken from the environment]
  D="$OUT/$1"; rm -rf "$D"; mkdir -p "$D"
  (cd "$D" && SERIAL_IN=../typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG=$2 \
     "$OUT/emu" "$ROM" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  python3 video3/bench/checkv3sd.py "$D" > "$D/paint.txt" 2>&1 \
    || { cat "$D/paint.txt"; echo "frames=0 painted=0 colours=0 changed=0" > "$D/paint.txt"; }
  rm -f "$D/frames.bin"      # ⚠ hundreds of megabytes, and already reduced
}

run card "$OUT/sd.img"
run nocard ""                # ⛔ SDIMG empty: machine.c reports CD = 0

get() { sed -n "s/.*$2=\([0-9]*\).*/\1/p" "$OUT/$1/paint.txt"; }
c_frames=$(get card frames);   c_painted=$(get card painted)
c_colours=$(get card colours); c_changed=$(get card changed)
n_frames=$(get nocard frames); n_painted=$(get nocard painted)

fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }
has()   { grep -q -- "$1" "$OUT/card/console.txt"; }
nohas() { ! grep -q -- "$1" "$OUT/card/console.txt"; }

echo
echo "      the card:   $(cat "$OUT/card/paint.txt")"
echo "      no card:    $(cat "$OUT/nocard/paint.txt")"
echo

# --- 1. the machine, and the card -----------------------------------------
claim "the machine booted to a shell"                          has '/DD:'
claim "the bootfile carries rbsd and its SD0 descriptor"       has 'rbsd'
# ⚠ ANCHORED: `dir /sd0/cmds` is echoed to the console as it is typed, so a
# bare grep for the demo's name passes with an empty socket.  run-sd.sh was
# caught by exactly this and its negative control is what caught it.
claim "⭐ /SD0 mounted: the root the host's os9 tools wrote"    has '^CMDS  *DATA'
claim "   and CMDS on the card holds the demo"                 has "^$DEMO  *libvid\\|^libvid  *$DEMO"

# --- 2. the ROM disk does not have it -------------------------------------
# asked of the machine...
claim "⛔ the ROM disk's CMDS does NOT carry $DEMO"             sh -c "! sed -n '/Directory of .DD.CMDS/,/^\$/p' '$OUT/card/console.txt' | grep -qw '$DEMO'"
claim "   but does carry the rescue set (format, dcheck, copy)" sh -c "grep -qw format '$OUT/card/console.txt' && grep -qw dcheck '$OUT/card/console.txt'"
# ...and of the image on the host, which is the arbiter: a `dir` that scrolled
# off, a name that wrapped a column, and the claim above would pass on nothing
claim "⛔ and the ROM disk IMAGE has no $DEMO either (the host asks)" \
  sh -c "os9 dir '$REC/romdisk.dsk',CMDS | grep -qw '$DEMO' && exit 1; exit 0"

# --- 3. it ran ------------------------------------------------------------
claim "no command failed: no Error # on the console"           nohas 'Error #'
claim "the run ended at the last command, not by the clock"    grep -q 'SERIAL_STOP seen' "$OUT/card/emu.txt"
claim "the CPU never ran through empty RAM (WILD)"             sh -c "! grep -q '^WILD' '$OUT/card/emu.txt'"
claim "no crash: nothing printed D.Crash's '!'"                sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/card/console.txt'"
claim "the emulator did not object"                            sh -c "! grep -q '^FAIL' '$OUT/card/emu.txt'"
claim "the card put a picture out at all (${c_frames:-0} frames recorded)" test "${c_frames:-0}" -gt 100
claim "⭐ THE DEMO PAINTED: ${c_painted:-0} frames of >12 colours, ${c_colours:-0} at once" \
  sh -c "test ${c_painted:-0} -ge 20 && test ${c_colours:-0} -ge 16"
claim "⭐ and it ANIMATED: the picture changed on ${c_changed:-0} frames, so it is a scene and not a splash" \
  test "${c_changed:-0}" -ge 20

# --- 4. ⛔ the negative control --------------------------------------------
nc() { grep -q -- "$1" "$OUT/nocard/console.txt"; }
claim "⛔ with an EMPTY socket the machine still boots"         nc '/DD:'
claim "⛔ and /SD0 refuses at 9.0 - E\$NotRdy, not silence"     nc 'Error #246'
claim "⛔ and the demo is NOT FOUND - E\$PNNF, not a hang"      nc 'Error #216'
# ⭐ AND IT IS STRONGER THAN "no colours": with no card the demo never runs,
# so nothing ever claims the screen and the emulator records NO FRAME AT ALL.
claim "⛔ and NOTHING was painted - ${n_frames:-?} frames, ${n_painted:-?} of them coloured" \
  sh -c "test ${n_painted:-1} -eq 0 && test ${n_frames:-1} -eq 0"
claim "⛔ and it FAILS rather than hanging - the run reached the end" \
  grep -q 'SERIAL_STOP seen' "$OUT/nocard/emu.txt"

echo
echo "      $n claims, $fail failed        (console in $OUT/card/console.txt)"
[ "$fail" -eq 0 ] || exit 1
