#!/bin/sh
# ⭐ THE DESKTOP, DRIVEN BY A MOUSE - arm6309 docs/boot-and-desktop.md §3,
# milestones 1 and 2.
#
#   sh video3/bench/run-v3desk.sh        ~3 min.  OUT=dir, NOBUILD=1, NORUN=1
#
# ⛔ WHAT LOOKED LIKE A DESKTOP UNTIL NOW WAS A RECORDING.  `v3desk`,
# `v3menu` and `v3paint` are scripted streams of CoArm escapes that
# software/nitros9/tools/v3show.py writes and `copy /sd0/data/v3desk /w3`
# plays; they are a faithful picture and nothing in them is clickable.  This
# bench runs the PROGRAM (nitros9 level2/arm6309/cmds/desk.asm) off the SD
# card and clicks at it with PS2_SCRIPT (software/demo/emu/ps2script.h) -
# timed, semantic mouse events fed to machine.c's line-level PS/2 devices
# rather than past them.
#
# What it has to establish, and every one of them off PIXELS rather than off
# a progress code the program printed about itself:
#
#   1  the menu bar is drawn WHERE IT SHOULD BE - its own grey across rows
#      0..17, one row of frame under it, the desktop below that, and type in
#      it.  Read out of the recorded frames, at coordinates parsed out of
#      desk.asm's own GEO equates
#   2  ⭐ A CLICK PULLS THE MENU DOWN AND THE PIXELS CHANGE: the pull-down's
#      rectangle differs from what was under it, and it was not a pull-down
#      one frame before the click
#   3  ⭐ MOVING OVER ITEMS MOVES THE HIGHLIGHT, and onto the item the
#      pointer is over - asserted for TWO different items, by sampling the
#      swatch inside each item's rectangle
#   4  clicking off the menu dismisses it and ⭐ RESTORES WHAT WAS
#      UNDERNEATH - the rectangle's CRC is the one it had before the menu
#      was ever opened, and desktop icons are deliberately under it
#   5  ⭐ A MENU ITEM FORKS ITS PROGRAM: Paint runs, and the claim is PAINT'S
#      OWN PICTURE on the card's output, not that a click happened
#   6  `stardew` is there, greyed, refuses the highlight, and CLICKING IT
#      LAUNCHES NOTHING
#   7  the KEYBOARD leg: `q` on the window's own keyboard ends the program,
#      read non-blocking so the loop never stalls on it
#   8  ⛔ THE NEGATIVE CONTROL: the same everything, and a script that walks
#      the bar and never clicks.  The menu must stay shut and the pull-down's
#      rectangle must hold exactly ONE picture for the whole run.  A desktop
#      that drew a menu on a timer would pass every claim above
#
# ⚠ THE POINTER IS IN THE PICTURE.  video3 composites the arrow as a
# hardware sprite, so every claim here is made about pixels the sprite is not
# on, and the two frames the restore test compares are both taken with the
# mouse parked away from the pull-down.  scripts/deskidle.ps2's header says
# why the control walks at y = 1 and not y = 8.
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3desk}
S="$ROOT/video3/bench/scripts"
DESKASM=${DESKASM:-}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-105}
IDLE_SECONDS=${IDLE_SECONDS:-50}
TICKS=${TICKS:-5000}                    # desk's iteration bound; Quit is what normally ends it
IDLETICKS=${IDLETICKS:-1200}            # the control's: it exits on the bound
KEY_SECONDS=${KEY_SECONDS:-40}
# ⛔ A BOUND THE RUN CANNOT REACH, on purpose: the keyboard run's DESK-BYE
# has to be the keystroke.  desk polls at a few hundred iterations a second,
# so 60,000 is minutes of machine time inside a forty-second run.
KEYTICKS=${KEYTICKS:-60000}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
[ -n "$DESKASM" ] || DESKASM="$NITROS9DIR/level2/arm6309/cmds/desk.asm"
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

[ -f "$DESKASM" ] || { echo "FAIL  no $DESKASM (../nitros9 on its arm6309 branch?)"; exit 1; }

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-v3desk.log" 2>&1 || {
    tail -20 "$OUT/mkrom-v3desk.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD: the shell, the app the menu launches, and the two games the
# menu offers.  They are on the card and NOT in the ROM disk, which is what
# `desk`'s launcher has to reach through the execution directory.
DATA="$OUT/data" sh software/nitros9/mksddisk.sh "$OUT/sd.img" desk v3paint monster pinball \
  > "$OUT/mksddisk.log" 2>&1 || { cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

# ⚠ CR, not LF.  ⛔ And `chx /sd0/cmds` comes last: after it the only things
# the shell can fork are the card's commands and shell+'s built-ins, which is
# exactly the arrangement the launcher has to work in.
STOP=$(printf '\nDONE-arm6309')
run() {   # run <dir> <ps2 script> <desk ticks> <seconds of machine>
  D="$OUT/$1"; rm -rf "$D"; mkdir -p "$D"
  printf 'iniz w3\rchd /sd0\rchx /sd0/cmds\rdesk /w3 %s\recho DONE-arm6309\r' "$3" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     PS2_SCRIPT="$S/$2" PS2_SCRIPT_GATE="DESK-READY" \
     "$OUT/emu" "$ROM" . "$4" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  python3 video3/bench/checkdesk.py "$DESKASM" "$D" > "$D/desk.txt" 2> "$D/desk.err" \
    || { cat "$D/desk.err"; echo "frames=0" > "$D/desk.txt"; }
  [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
}

if [ -z "$NORUN" ]; then
  run click desk.ps2     "$TICKS"     "$SECONDS_OF_MACHINE"
  run idle  deskidle.ps2 "$IDLETICKS" "$IDLE_SECONDS"
  run key   deskkey.ps2  "$KEYTICKS"  "$KEY_SECONDS"
fi
# ⚠ NORUN=1 re-reads the claims from the last run's files.  For working on
# the claims, never for reporting a pass.
[ -f "$OUT/click/desk.txt" ] || { echo "FAIL  no run to read (drop NORUN)"; exit 1; }

fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }
# ⛔ NEVER THROUGH `sh -c`: a shell function is invisible to it and
# `! <not found>` is TRUE (CLAUDE.md).  Every helper here is called directly.
get()  { tr ' ' '\n' < "$OUT/$1/desk.txt" | sed -n "s/^$2=\(.*\)$/\1/p" | head -1; }
field() { awk -v k="$2" -v f="$3=" '$1 == k { for (i = 1; i <= NF; i++)
            if (index($i, f) == 1) { sub(/^[^=]*=/, "", $i); print $i } }' "$OUT/$1/desk.txt"; }
has()  { grep -q -- "$2" "$OUT/$1/console.txt"; }
nohas() { grep -q -- "$2" "$OUT/$1/console.txt" && return 1; return 0; }
nolog() { grep -q -- "$2" "$OUT/$1/emu.txt" && return 1; return 0; }
# ⚠ seconds are not integers, so `test -gt` cannot compare them - and an
# EMPTY value has to fail rather than compare as zero
gt()   { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a != "" && b != "" && a + 0 > b + 0) }'; }
# ⭐ EVERY rest whose pointer stopped at X,Y, and what was highlighted at each
# one, reduced to the distinct answers.  The script visits some of them twice,
# and one answer that disagrees with the other has to show up here rather than
# be hidden by taking the last.  "none" means the pointer never rested there,
# which fails every claim below rather than passing an empty one.
hiat() { awk -v xx="x=$2" -v yy="y=$3" '$1 ~ /^H[0-9]+$/ && $3 == xx && $4 == yy {
           h = $5; sub(/^hi=/, "", h); print h; found = 1 }
         END { if (!found) print "none" }' "$OUT/$1/desk.txt" \
         | sort -u | tr '\n' '/' | sed 's|/$||'; }

echo
sed -n '1,/^clicks=/p' "$OUT/click/desk.txt" | sed 's/^/      /'
grep -E '^(C|H|restore|paintafter|mg)' "$OUT/click/desk.txt" | sed 's/^/      /'
echo "      idle: $(grep '^frames=' "$OUT/idle/desk.txt")"
echo "      key:  $(grep '^frames=' "$OUT/key/desk.txt")"
echo

# --- 0. the machine, the card, and the program ----------------------------
claim "the machine booted to a shell"                          has click '/DD:'
claim "⭐ /SD0 mounted and the desktop shell ran off it"        has click 'DESK-READY'
claim "the run ended at the last command, not by the clock"    grep -q 'SERIAL_STOP seen' "$OUT/click/emu.txt"
claim "the CPU never ran through empty RAM (WILD)"             nolog click '^WILD'
claim "no crash: nothing printed D.Crash's '!'"                nohas click '![0-9A-F][0-9A-F]'
claim "every event in the script was delivered"                grep -q 'all [0-9]* events delivered' "$OUT/click/emu.txt"
claim "⭐ and the pointer the MACHINE rebuilt is where the script said" \
  test "$(get click mg)" = ok
claim "the card put a picture out ($(get click frames) frames)" \
  test "$(get click frames)" -gt 300

# --- 1. the menu bar, as pixels -------------------------------------------
claim "⭐ THE MENU BAR IS WHERE IT SHOULD BE: its grey over rows 0..17, a frame rule at 18, the desktop at 25 ($(get click barok) frames)" \
  test "$(get click barok)" -ge 200
claim "⭐ and there is TYPE in it - the two titles' ink ($(get click barink) frames)" \
  test "$(get click barink)" -ge 200

# --- 2. the click that pulls it down --------------------------------------
claim "⭐ THE MENU WAS SHUT BEFORE THE FIRST CLICK"             test "$(field click C0 pre)" = shut
claim "⭐ AND THE CLICK PULLED IT DOWN"                         test "$(field click C0 post)" = open
claim "⭐ and the pull-down's PIXELS CHANGED: $(field click C0 chg)% of its rectangle differs from what was under it" \
  test "$(field click C0 chg)" -ge 50

# --- 3. the highlight follows the pointer ---------------------------------
# ⚠ the swatch is inside the item's own highlight rectangle and 90 px left of
# the pointer, so what is read is the highlight and never the sprite
claim "⭐ HOVERING ITEM 0 (Paint) HIGHLIGHTS ITEM 0, AND ONLY IT" \
  test "$(hiat click 168 32)" = 0
claim "⭐ AND MOVING TO ITEM 1 (Monsterland) MOVES THE HIGHLIGHT THERE - a different item" \
  test "$(hiat click 168 52)" = 1
claim "⛔ and hovering the GREYED item highlights nothing at all" \
  test "$(hiat click 168 92)" = -

# --- 4. dismissal, and what was underneath --------------------------------
claim "clicking off the menu dismissed it"                     test "$(field click C1 post)" = shut
claim "⭐ AND RESTORED WHAT WAS UNDERNEATH, pixel for pixel: the rectangle's CRC is the one it had before the menu existed ($(get click basecrc) / $(get click postcrc))" \
  test "$(get click restore)" = ok

# --- 5. ⭐ the launcher ----------------------------------------------------
claim "the Paint item asked for v3paint by name"               has click 'DESK-RUN Paint'
claim "⭐ AND v3paint RAN: its own page reached the card's output on $(get click paint) frames" \
  test "$(get click paint)" -ge 20
claim "   ...and it says so itself, on the standard error it inherited"  has click 'V3PAINT-DREW'
claim "⭐ and it was THE CLICK ON THE ITEM that did it - click $(get click paintafter) of the session" \
  test "$(get click paintafter)" = 3
claim "⭐ and the DESKTOP CAME BACK: the menu bar is drawn again at $(get click deskback) s, after Paint's last frame at $(get click paint1) s" \
  gt "$(get click deskback)" "$(get click paint1)"
# ⛔ THE SCHEDULING PRECONDITION, STATED AS A CLAIM.  A child owns the screen
# and the desktop sleeps in F$Wait while it runs, so a click sent before the
# repaint has finished reaches nobody - and every claim after this one would
# fail with no hint why.  scripts/desk.ps2's `at 60.000` is what puts phase 3
# after it; this is what says it landed there.
claim "⛔ ...and the script's next click ($(field click C4 t) s) came AFTER that, not during the child" \
  gt "$(field click C4 t)" "$(get click deskback)"
claim "the desktop's own state survived the launch: the menu was shut again" \
  test "$(field click C4 pre)" = shut
claim "   and the menu bar's own rectangle survived the launch"  test "$(field click C4 post)" = open

# --- 6. ⛔ specified and not built -----------------------------------------
claim "⛔ Stardew is on the menu, and the source declares it greyed" \
  grep -q '^item 1 3 0 Stardew' "$OUT/click/desk.txt"
claim "⛔ clicking it dismisses the menu"                       test "$(field click C5 post)" = shut
claim "⛔ AND LAUNCHES NOTHING: the console says it was asked for and refused" \
  has click 'DESK-DIS Stardew'
claim "⛔ ...and never says it was run"                         nohas click 'DESK-RUN Stardew'
claim "⛔ and no second program drew: Paint's picture was on the card exactly ONCE ($(get click paintruns) run)" \
  test "$(get click paintruns)" = 1

# --- 7. quit, through the menu that offers it -----------------------------
claim "the Quit item ended the program"                        has click 'DESK-BYE'
claim "   and the shell got its prompt back and ran the next command"  has click 'DONE-arm6309'

# --- 8. the keyboard ------------------------------------------------------
# ⭐ desk's bound here is $KEYTICKS iterations, which it could not reach in
# $KEY_SECONDS s of machine - so DESK-BYE at all is the keystroke.
claim "⭐ the keyboard run drew the desktop too"                 has key 'DESK-READY'
claim "⭐ AND THE KEY q ON THE WINDOW'S OWN KEYBOARD ENDED IT, inside a run its iteration bound could not reach" \
  has key 'DESK-BYE'
claim "   ...and the shell got the machine back"                has key 'DONE-arm6309'
claim "⛔ and the desktop STAYED PUT under it: the pull-down's rectangle held one picture, and nothing was launched" \
  test "$(get key dropcrcs)" = 1
claim "⛔ ...and no menu came down and nothing was highlighted either" \
  test "$(get key open)$(get key hiany)" = 00

# --- 9. ⛔ THE NEGATIVE CONTROL -------------------------------------------
# The same ROM, the same card, the same program - and a mouse that walks the
# bar and never presses anything.
claim "⛔ the control ran the desktop too"                      has idle 'DESK-READY'
claim "⛔ and it ended on its own iteration bound, not by the clock"  has idle 'DESK-BYE'
claim "⛔ and the script moved the mouse ($(get idle rests) rest positions)" \
  test "$(get idle rests)" -ge 5
claim "⛔ AND PRESSED NOTHING: no click reached the machine"    test "$(get idle clicks)" = 0
claim "⛔ SO NO MENU WAS EVER OPENED - not one frame of a pull-down" \
  test "$(get idle open)" = 0
claim "⛔ AND NOTHING WAS EVER HIGHLIGHTED"                     test "$(get idle hiany)" = 0
claim "⛔ AND THE SCREEN DID NOT CHANGE: the pull-down's rectangle held ONE picture for the whole run" \
  test "$(get idle dropcrcs)" = 1
claim "⛔ and no program was launched"                          nohas idle 'DESK-RUN'
claim "⛔ ...and the control still DREW the desktop, so a blank screen is not what passed it ($(get idle barok) frames of menu bar)" \
  test "$(get idle barok)" -ge 200

echo
echo "      $n claims, $fail failed        (logs in $OUT)"
[ "$fail" -eq 0 ] || exit 1
