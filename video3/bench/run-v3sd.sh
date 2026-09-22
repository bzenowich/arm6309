#!/bin/sh
# ⭐ A DEMO THAT IS NOT IN THE ROM, RUN OFF THE SD CARD.
#
#   sh video3/bench/run-v3sd.sh          ~3 min (the card run is 130 machine s).
#                                        OUT=dir, DEMO=name, DEMOARGS=..., NOBUILD=1
#
# Until 2026-09-20 every demo program AND all of its data were inside the boot
# ROM's 488 K RBF image.  The image was FULL, and a scene had to ask the recipe
# for its command and give back the room (CMDS_EXTRA / CMDS_DROP); /DD/SYS
# alone was 1,140 of the 1,952 sectors, and all of it pictures.  The machine
# has storage now - an SD card at $FF58, the rbsd driver, /SD0 (storage/docs/
# sdcard.md §9.4) - so the programs AND their data moved onto a card, and the
# ROM disk is a rescue system: the kernel, the shell, the shared modules,
# errmsg, and enough commands to format a card and fill it.
#
# ⭐ THIS BENCH IS ABOUT WHERE THE PROGRAM CAME FROM, not about the scene.  It
# runs a few frames and no more; run-v3mv.sh is what measures the scene.  The
# four things it has to establish are:
#
#   1. the machine boots and /SD0 mounts - the host's os9 tools wrote the
#      image and NitrOS-9's RBF reads it, two implementations agreeing
#   2. ⭐ THE HAIKU DESKTOP AND PAINT WERE DRAWN FROM THE CARD, and a demo
#      program LOADED AND RAN.  Not that the commands were typed: that a
#      desktop's shape and Paint's page reached the card's output, which is
#      checkv3sd.py's `desk` and `paint` counts.  ⭐ And `changefont` for the
#      other half - a program opening a data file for ITSELF, through DOpen's
#      card-then-ROM search
#   3. the ROM disk does NOT carry that demo - asked of the machine
#      (`dir /dd/cmds`) and of the image on the host, because if it were
#      still in the ROM the run above would prove nothing at all
#   4. ⛔ THE NEGATIVE CONTROL: the same ROM, the same keystrokes, and NO
#      CARD IN THE SOCKET.  /SD0 must refuse at 9.0, every stream and every
#      program must fail to find what it needs and SAY SO, and the run must
#      REACH THE END rather than hang - a bench that hangs on a missing card
#      cannot tell a missing card from a slow one.
#      ⛔ AND A BLANK SCREEN IS NOT A PASS.  `iniz w3` and `display 1b 21`
#      need no card, so the control still SELECTS screens and the emulator
#      still records eleven hundred frames of them.  `desk` and `paint` must
#      both be zero: the frames are there and there is nothing on them.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3sd}
DEMO=${DEMO:-mvania}
# ⚠ changefont goes on the card too: it is the program whose DATA moved, so it
# is what exercises DOpen's card-then-ROM search from the machine's side.
DEMOS=${DEMOS:-"$DEMO changefont"}
# mvania's arguments: mode 0 (the scene as designed), two frames a step - its
# sweep is fourteen steps, so this is 28 frames of scene, which is all this
# bench wants - and SS.CopyN's 1,393-byte fixed cost (run-v3mv.sh §).
DEMOARGS=${DEMOARGS:-"0 2 1393"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-220}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-v3sd.log" 2>&1 || {
    tail -20 "$OUT/mkrom-v3sd.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD, MADE BY THE TOOLCHAIN.  One demo and nothing else: the image is
# sized to what it is given, so this is ~30 KB rather than the 100 KB a full
# demo card is, and a short one would fail loudly there rather than quietly
# here (software/nitros9/mksddisk.sh).
DATA="$OUT/data" sh software/nitros9/mksddisk.sh "$OUT/sd.img" $DEMOS > "$OUT/mksddisk.log" 2>&1 || {
  cat "$OUT/mksddisk.log"; echo "FAIL  the demo card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c software/demo/emu/hd6309.c "$ROOT/audio/refplayer/card.c"

# ⚠ CR, not LF (demo-report.md §15.3).
#
# ⛔ EVERY `copy` AND `display` COMES BEFORE `chx`, and that is not tidiness:
# `chx /sd0/cmds` moves the EXECUTION directory, and after it the only things
# the shell can fork are the card's own commands and shell+'s merged built-ins
# (echo, iniz, load, link).  `copy`, `dir` and `display` live in /DD/CMDS and
# become unfindable - which is itself part of what the split means.
#
# ⭐ THE HAIKU DESKTOP AND PAINT are `copy`d from the card, exactly as
# software/nitros9/video/session3.py copies them from /DD/SYS: the ROM
# toolbox draws them, and the stream is the only thing that moved.
# ⭐ `changefont` is the OTHER half - a program that opens a data file for
# ITSELF.  A bare name goes through DOpen (card first, /DD/SYS after), and
# the second call gives an explicit path to a face that does not exist, which
# must fail: an override the caller asks for is not second-guessed.
printf 'dir /sd0\rdir /sd0/cmds\rdir /sd0/data\rdir /dd/cmds\rdir /dd/sys\r' > "$OUT/typed.txt"
printf 'iniz w3\rcopy /sd0/data/v3desk /w3\rcopy /sd0/data/v3cmds /w3\r' >> "$OUT/typed.txt"
printf 'iniz w4\rcopy /sd0/data/v3paint /w4\rcopy /sd0/data/v3draw /w4\r' >> "$OUT/typed.txt"
printf 'display 1b 24 >/w4\rdisplay 1b 24 >/w3\r' >> "$OUT/typed.txt"
printf 'iniz w1\rdisplay 1b 21 >/w1\r' >> "$OUT/typed.txt"
printf 'chd /sd0\rchx /sd0/cmds\r' >> "$OUT/typed.txt"
printf 'changefont uncial >/w1\rchangefont /sd0/data/nosuchface >/w1\r' >> "$OUT/typed.txt"
printf 'iniz w5\r%s %s >/w5\recho DONE-arm6309\r' "$DEMO" "$DEMOARGS" >> "$OUT/typed.txt"

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
  [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"   # ⚠ hundreds of megabytes, already reduced
}

if [ -z "$NORUN" ]; then
  run card "$OUT/sd.img"
  run nocard ""              # ⛔ SDIMG empty: machine.c reports CD = 0
fi
# ⚠ NORUN=1 re-reads the claims from the consoles and paint.txt of the last
# run.  It is for working on the claims, never for reporting a pass.
[ -f "$OUT/card/console.txt" ] || { echo "FAIL  no run to read (drop NORUN)"; exit 1; }

get() { sed -n "s/.*$2=\([0-9]*\).*/\1/p" "$OUT/$1/paint.txt"; }
c_frames=$(get card frames);   c_painted=$(get card painted)
c_colours=$(get card colours); c_changed=$(get card changed)
c_desk=$(get card desk);       c_paint=$(get card paint)
n_frames=$(get nocard frames); n_painted=$(get nocard painted)
n_desk=$(get nocard desk);     n_paint=$(get nocard paint)

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
# ⚠ EVERY LISTING CLAIM IS SCOPED TO ITS OWN `Directory of` BLOCK.  `dir` is
# echoed to the console as it is typed, so a bare grep for a name matches the
# COMMAND LINE and passes with an empty socket.  run-sd.sh was caught by
# exactly that; `indir` below is the fix, and the negative control is what
# would catch it again.
# ⛔ awk AND NOT sed: the directory name HAS SLASHES IN IT, and
# `sed -n "/Directory of $1 /,..."` makes them regex delimiters - the address
# is a syntax error, sed prints nothing, and every listing claim fails while
# the machine was perfectly correct.  index() takes the string as a string.
indir() {   # indir <dir, as `dir` prints it> <name>
  awk -v d="Directory of $1 " -v n="$2" '
    index($0, d) { inblk = 1; next }
    inblk && NF == 0 { inblk = 0 }
    inblk { for (i = 1; i <= NF; i++) if ($i == n) found = 1 }
    END { exit !found }' "$OUT/card/console.txt"
}
# ⛔ AND THEY ARE CALLED DIRECTLY, NEVER THROUGH `sh -c`.  A shell FUNCTION is
# not exported to `sh -c`, so `sh -c "indir /dd/sys v3desk"` runs a shell that
# says "indir: not found" and exits 127 - which makes the POSITIVE form fail
# honestly and the NEGATIVE form `! indir ...` PASS VACUOUSLY.  Three claims
# here did exactly that on 2026-09-20, and the one that "passed" was the one
# asserting the ROM disk no longer carries the desktop.
indirall()  { d=$1; shift; for nm in "$@"; do indir "$d" "$nm" || return 1; done; return 0; }
noneindir() { d=$1; shift; for nm in "$@"; do indir "$d" "$nm" && return 1; done; return 0; }
claim "the machine booted to a shell"                          has '/DD:'
claim "the bootfile carries rbsd and its SD0 descriptor"       has 'rbsd'
claim "⭐ /SD0 mounted: the root the host's os9 tools wrote"    has '^CMDS  *DATA'
claim "   and CMDS on the card holds $DEMO and changefont"     indirall /sd0/cmds "$DEMO" changefont
claim "⭐ and DATA on the card holds the desktop and Paint"     indirall /sd0/data v3desk v3paint v3draw

# --- 2. the ROM disk does not have any of it ------------------------------
# asked of the machine...
claim "⛔ the ROM disk's CMDS does NOT carry $DEMO"             noneindir /dd/cmds "$DEMO"
claim "   but does carry the rescue set (format, dcheck, copy)" indirall /dd/cmds format dcheck copy makdir
claim "⛔ and /DD/SYS carries neither the desktop nor Paint"    noneindir /dd/sys v3desk v3paint v3draw
claim "⛔ nor the face changefont just read off the card"       noneindir /dd/sys font.uncial
claim "   what is left in /DD/SYS is errmsg, which the shell needs to print an error at all" \
  indir /dd/sys errmsg
# ...and of the images on the host, which are the arbiter: a `dir` that
# scrolled off and the claims above pass on nothing
claim "⛔ and the ROM disk IMAGE has no $DEMO either (the host asks)" \
  sh -c "os9 dir '$REC/romdisk.dsk',CMDS | grep -qw -- '$DEMO' && exit 1; exit 0"
claim "⛔ and its /DD/SYS is errmsg ALONE (the host asks)" \
  sh -c "test \"\$(os9 dir '$REC/romdisk.dsk',SYS | grep -c '[A-Za-z]')\" -le 2"

# --- 3. it ran ------------------------------------------------------------
# ⛔ ONE error is expected and it is deliberate: `changefont /sd0/data/nosuchface`
# gives an explicit path to a face that is not there, and an override the
# caller asks for is not second-guessed.  ⭐ TWO would mean the FIRST
# changefont - a bare name, which goes through DOpen - had not found its face
# on the card, so this count is the positive claim about DOpen as well.
nerr=$(grep -c 'Error #' "$OUT/card/console.txt")
claim "⭐ exactly one error, the deliberate bad path (got ${nerr:-?}); a bare name that missed would make two" \
  test "${nerr:-0}" -eq 1
claim "   and it is E\$PNNF on the path the caller gave"       has 'Error #216'
claim "the run ended at the last command, not by the clock"    grep -q 'SERIAL_STOP seen' "$OUT/card/emu.txt"
claim "the CPU never ran through empty RAM (WILD)"             sh -c "! grep -q '^WILD' '$OUT/card/emu.txt'"
claim "no crash: nothing printed D.Crash's '!'"                sh -c "! grep -q '![0-9A-F][0-9A-F]' '$OUT/card/console.txt'"
claim "the emulator did not object"                            sh -c "! grep -q '^FAIL' '$OUT/card/emu.txt'"
claim "the card put a picture out at all (${c_frames:-0} frames recorded)" test "${c_frames:-0}" -gt 100
claim "⭐ THE HAIKU DESKTOP CAME OFF THE CARD: ${c_desk:-0} frames of a desktop's shape" \
  test "${c_desk:-0}" -ge 20
claim "⭐ AND PAINT DID: ${c_paint:-0} frames with its page on them"  test "${c_paint:-0}" -ge 20
claim "⭐ and the demo painted: ${c_painted:-0} frames of >12 colours, ${c_colours:-0} at once" \
  sh -c "test ${c_painted:-0} -ge 20 && test ${c_colours:-0} -ge 16"
claim "⭐ and it ANIMATED: the picture changed on ${c_changed:-0} frames, so it is a scene and not a splash" \
  test "${c_changed:-0}" -ge 20

# --- 4. ⛔ the negative control --------------------------------------------
nc() { grep -q -- "$1" "$OUT/nocard/console.txt"; }
claim "⛔ with an EMPTY socket the machine still boots"         nc '/DD:'
claim "⛔ and /SD0 refuses at 9.0 - E\$NotRdy, not silence"     nc 'Error #246'
claim "⛔ and the demo is NOT FOUND - E\$PNNF, not a hang"      nc 'Error #216'
# ⭐ DOpen's SECOND leg, asserted: a bare name misses the card AND misses
# /DD/SYS, so changefont reports the ROM's E$PNNF and not the card's E$NotRdy.
# ⚠ If the build had kept the faces in ROM (SYSROM), this would pass silently
# for the wrong reason - which is why the /DD/SYS claims above are here.
claim "⛔ and changefont's bare name misses BOTH legs of DOpen" \
  test "$(grep -c 'Error #216' "$OUT/nocard/console.txt")" -ge 2
# ⛔ AND THE ONE THAT MATTERS: the screens are still opened and selected with
# no card - `iniz w3` and `display 1b 21` do not need one - so the emulator
# records over a thousand frames of a BLANK SCREEN.  A blank screen is not a
# pass, and the shape counts are what say so.
claim "⛔ and NOTHING was drawn on them: ${n_frames:-?} frames, ${n_painted:-?} coloured, desk ${n_desk:-?}, paint ${n_paint:-?}" \
  sh -c "test ${n_painted:-1} -eq 0 && test ${n_desk:-1} -eq 0 && test ${n_paint:-1} -eq 0"
claim "⛔ and it FAILS rather than hanging - the run reached the end" \
  grep -q 'SERIAL_STOP seen' "$OUT/nocard/emu.txt"

echo
echo "      $n claims, $fail failed        (console in $OUT/card/console.txt)"
[ "$fail" -eq 0 ] || exit 1
