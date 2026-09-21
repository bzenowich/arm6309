#!/bin/sh
# ⭐ THE FILE MANAGER, CLICKED AT - arm6309 docs/boot-and-desktop.md §3,
# milestone 3.
#
#   sh video3/bench/run-v3files.sh       ~11 min.  OUT=dir, NOBUILD=1, NORUN=1
#
# `desk` (nitros9 level2/arm6309/cmds/desk.asm) grew a Tracker window that
# lists a REAL directory, enters one, goes back up, scrolls, and forks what
# is clicked.  This boots the machine, runs it off the SD card and drives it
# with a PS2_SCRIPT, and then reads every answer off the recorded FRAMES.
#
# ⭐ THE LISTING IS COMPARED WITH THE HOST'S `os9 dir`, NOT WITH A LIST TYPED
# HERE.  checkfiles.py rebuilds each candidate name out of the ROM's OWN font
# blob (mktbox.py wrote it) and matches it against the pixels of each row, so
# what is printed is what the machine DREW; the claims below then compare
# that with what the tool that WROTE the image says is on it.  Two
# independent readers of the same directory, and the pixels in between.
#
# What it has to establish:
#
#   1  ⭐ A DESKTOP ICON IS CLICKABLE - one click on the disk SELECTS it and
#      opens nothing, a second click brings the manager up on /SD0.  That is
#      docs/boot-and-desktop.md §5 item 6
#   2  the window is drawn with the toolbox's chrome where desk.asm's FM.*
#      say, and its title is the directory
#   3  ⭐ THE LIST IS THE DIRECTORY'S REAL CONTENTS, off the pixels
#   4  ⭐ clicking a directory ENTERS it and the list becomes that
#      directory's contents; the scroll bar's arrow moves the list; Go > Up
#      returns to the parent
#   5  ⭐ OPENING A PROGRAM FROM THE LIST RUNS IT, and the claim is Paint's
#      own picture on the card's output, not that a click happened - and the
#      MANAGER COMES BACK afterwards, out of desk's own table
#   6  ⛔ THE NEGATIVE CONTROL: the same everything, the window already up on
#      /SD0/DATA, and a mouse that walks the list, both scroll arrows, the
#      menu bar and the disk icon and never presses.  The list must hold
#      exactly ONE picture, nothing may be selected, nothing entered, nothing
#      launched - and the one picture it holds must still be the real listing
#   7  ⭐ v3trk, THE OTHER SIDE OF THE SHARED READER.  desk and v3trk include
#      the same modules/v3dir.inc since 2026-09-21; the third run drives
#      v3trk into the SAME rectangle from the shell and reads its list with
#      the same code, so the refactor cannot quietly break the program it
#      came out of
#
# ⛔ The exit code is the answer.
set -e
cd "$(dirname "$0")/../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-v3files}
S="$ROOT/video3/bench/scripts"
DESKASM=${DESKASM:-}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-245}
IDLE_SECONDS=${IDLE_SECONDS:-70}
TRK_SECONDS=${TRK_SECONDS:-50}
# ⚠ HOW LONG AFTER A CLICK THE SCREEN IS READ, and it is not a guess: the
# first run of this bench sampled at three seconds and caught the list TEN
# ROWS INTO A TWELVE-ROW REDRAW - a listing that was right and half drawn,
# which reads exactly like a listing that is wrong.  Entering a directory is
# a read off the card and then a whole window; seven seconds is what covers
# it, and files.ps2 leaves ten between the clicks it matters for.
SAMPLE_AT=${SAMPLE_AT:-7.0}; export SAMPLE_AT
# ⛔ A BOUND THE RUN CANNOT REACH, on purpose: Quit is what ends the driven
# run, so DESK-BYE arriving is the menu and never the clock
TICKS=${TICKS:-60000}
IDLETICKS=${IDLETICKS:-1200}            # the control's: it exits on the bound
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
[ -n "$DESKASM" ] || DESKASM="$NITROS9DIR/level2/arm6309/cmds/desk.asm"
TOOLS=${TOOLS:-$ROOT/.tools/bin}
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

[ -f "$DESKASM" ] || { echo "FAIL  no $DESKASM (../nitros9 on its arm6309 branch?)"; exit 1; }

# ⭐ the geometry, out of desk.asm - the shell needs it to aim v3trk at the
# same rectangle, and nothing here transcribes a number
eval "$(python3 video3/bench/checkfiles.py --geom "$DESKASM")"

if [ -z "$NOBUILD" ]; then
  V3=1 sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom-v3files.log" 2>&1 || {
    tail -20 "$OUT/mkrom-v3files.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }

# ⭐ THE CARD.  CMDS is named in an order this bench depends on (v3paint is
# the second entry), and is CLAIMED below rather than assumed.  ⚠ DATA is a
# CURATED subset and not $OUT/data's 58 files: the manager holds FM.MAX
# entries and a directory that overflows it is a different test - this one
# wants twenty, which is more than the twelve rows that show and fewer than
# the table.  v3paint's own stream has to be among them, because that is what
# the program the bench launches opens.
FD="$OUT/fdata"
rm -rf "$FD"; mkdir -p "$FD"
cp "$OUT/data/v3paint" "$FD/" || { echo "FAIL  no v3paint stream in $OUT/data"; exit 1; }
i=0
for f in "$OUT"/data/font.*; do
  i=$((i + 1)); [ "$i" -le 19 ] && cp "$f" "$FD/"
done
[ "$(ls -1 "$FD" | wc -l)" -eq 20 ] || { echo "FAIL  the curated DATA is not 20 files"; exit 1; }

DATA="$FD" sh software/nitros9/mksddisk.sh "$OUT/sd.img" desk v3paint monster pinball v3trk \
  > "$OUT/mksddisk.log" 2>&1 || { cat "$OUT/mksddisk.log"; echo "FAIL  the card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

# ---------------------------------------------------------------------------
# ⭐ WHAT IS REALLY ON THE IMAGE, from the tool that wrote it.  `os9 dir`
# lists a directory in the order RBF keeps it, which is the order the machine
# reads it in, so these are both the CANDIDATE ALPHABET the pixel matcher is
# allowed and the expected answer.
oslist() { os9 dir "$1" | grep -v 'Directory of' | tr -s ' ' '\n' | grep -v '^$'; }
oslist "$OUT/sd.img"        > "$OUT/root.txt"
oslist "$OUT/sd.img,CMDS"   > "$OUT/cmds.txt"
oslist "$OUT/sd.img,DATA"   > "$OUT/data.txt"
cat "$OUT/root.txt" "$OUT/cmds.txt" "$OUT/data.txt" | sort -u > "$OUT/names.txt"
# rows <file> <skip> - the FM_ROWS names a page of that listing shows
rows() { sed -n "$(( $2 + 1 )),$(( $2 + FM_ROWS ))p" "$1" | tr '\n' ',' | sed 's/,$//'; }
ROOTROWS=$(rows "$OUT/root.txt" 0)
CMDSROWS=$(rows "$OUT/cmds.txt" 0)
DATAROWS=$(rows "$OUT/data.txt" 0)
DATAROW2=$(rows "$OUT/data.txt" 2)
DATAROW3=$(rows "$OUT/data.txt" 3)
NDATA=$(wc -l < "$OUT/data.txt" | tr -d ' ')
NROOT=$(wc -l < "$OUT/root.txt" | tr -d ' ')

cc -O2 -Wall -I"$ROOT/audio/refplayer" -o "$OUT/emu" software/demo/emu/machine.c \
   software/demo/emu/cpu6809.c "$ROOT/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
# run <dir> <ps2 script or -> <typed commands> <seconds of machine>
run() {
  D="$OUT/$1"; rm -rf "$D"; mkdir -p "$D"
  printf '%s' "$3" > "$D/typed.txt"
  if [ "$2" = "-" ]; then PS=""; GATE=""; else PS="$S/$2"; GATE="DESK-READY"; fi
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
     PS2_SCRIPT="$PS" PS2_SCRIPT_GATE="$GATE" \
     "$OUT/emu" "$ROM" . "$4" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" > "$D/emu.txt"
  python3 video3/bench/checkfiles.py "$DESKASM" "$D" "$OUT/names.txt" \
    > "$D/files.txt" 2> "$D/files.err" \
    || { cat "$D/files.err"; echo "frames=0" > "$D/files.txt"; }
  [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
}

# ⚠ CR, not LF.  ⛔ And `chx /sd0/cmds` comes last, as run-v3desk.sh's does:
# after it the only things the shell can fork are the card's commands.
PRE='iniz w3\rchd /sd0\rchx /sd0/cmds\r'
# ⚠ RUNS= re-does only the named ones, for working on the claims.  A run
# that is skipped is read from the last time it went, exactly as NORUN=1
# reads all three - never for reporting a pass.
RUNS=${RUNS:-"click idle trk"}
has_run() { case " $RUNS " in *" $1 "*) return 0 ;; esac; return 1; }
if [ -z "$NORUN" ]; then
  if has_run click; then run click files.ps2 \
    "$(printf "${PRE}desk /w3 %s\recho DONE-arm6309\r" "$TICKS")" "$SECONDS_OF_MACHINE"; fi
  if has_run idle; then run idle filesidle.ps2 \
    "$(printf "${PRE}desk /w3 %s /SD0/DATA\recho DONE-arm6309\r" "$IDLETICKS")" "$IDLE_SECONDS"; fi
  # ⭐ v3trk into desk's own rectangle: DWSet 640x480, Select, the toolbox
  # palette, then the list.  The escapes are CoArm's (ca_scr.asm) and the
  # numbers are desk.asm's, through the eval above.
  # ⛔ AND `display` COMES BEFORE `chx /sd0/cmds`, not after: chx moves the
  # EXECUTION directory to the card, and `display` lives in the ROM disk's
  # /DD/CMDS - after the chx the shell answers "Path Name Not Found" and the
  # screen is never set up, which reads as a broken v3trk.
  # ⚠ EXPORTED, not prefixed: `VAR=v func` on a shell FUNCTION is one of the
  # places POSIX leaves it to the shell, and the value has to reach python.
  ROW_DY=0; export ROW_DY
  if has_run trk; then run trk - "$(printf "iniz w3\rdisplay 1b 20 13 00 00 50 3c 01 06 06 >/w3\rdisplay 1b 21 >/w3\rdisplay 1b 6a 07 00 >/w3\rchd /sd0\rchx /sd0/cmds\rv3trk /sd0/cmds %d %d %d %d 1 %d %d %d %d >/w3\recho TRK-DONE\recho DONE-arm6309\r" \
       "$FM_LX" "$FM_LY" "$FM_LW" "$FM_LH" "$((FM_CX + 6))" "$((FM_SY + 1))" "$FM_DIC" "$FM_FIC")" \
    "$TRK_SECONDS"; fi
  unset ROW_DY
fi
# ⚠ NORUN=1 re-reads the claims from the last run's files.  For working on
# the claims, never for reporting a pass.
[ -f "$OUT/click/files.txt" ] || { echo "FAIL  no run to read (drop NORUN)"; exit 1; }

fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }
# ⛔ NEVER THROUGH `sh -c`: a shell function is invisible to it and
# `! <not found>` is TRUE (CLAUDE.md).  Every helper here is called directly.
get()  { tr ' ' '\n' < "$OUT/$1/files.txt" | sed -n "s/^$2=\(.*\)$/\1/p" | head -1; }
field() { awk -v k="$2" -v f="$3=" '$1 == k { for (i = 1; i <= NF; i++)
            if (index($i, f) == 1) { sub(/^[^=]*=/, "", $i); print $i } }' "$OUT/$1/files.txt"; }
has()  { grep -q -- "$2" "$OUT/$1/console.txt"; }
nohas() { grep -q -- "$2" "$OUT/$1/console.txt" && return 1; return 0; }
nolog() { grep -q -- "$2" "$OUT/$1/emu.txt" && return 1; return 0; }
# ⛔ grep -o, NOT grep -c.  desk's messages end in C$CR and the bench strips
# the CR, so the whole console is ONE LINE - `grep -c` would answer 1 however
# many times the thing happened, which is exactly the claim's own answer.
count() { test "$(grep -o -- "$3" "$OUT/$1/console.txt" | wc -l | tr -d ' ')" = "$2"; }
gt()   { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a != "" && b != "" && a + 0 > b + 0) }'; }
lt()   { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a != "" && b != "" && a + 0 < b + 0) }'; }
inrange() { awk -v a="$1" -v lo="$2" -v hi="$3" 'BEGIN { exit !(a != "" && a+0 >= lo && a+0 <= hi) }'; }

echo
sed -n '1,/^clicks=/p' "$OUT/click/files.txt" | sed 's/^/      /'
grep -E '^(S[0-9E]|A17|paint0)' "$OUT/click/files.txt" | sed 's/^/      /'
echo "      idle: $(grep '^frames=' "$OUT/idle/files.txt")"
grep -E '^SE' "$OUT/idle/files.txt" | sed 's/^/      idle  /'
grep -E '^SE' "$OUT/trk/files.txt" | sed 's/^/      trk   /'
echo "      os9:  root=$ROOTROWS  cmds=$CMDSROWS"
echo "            data=$DATAROWS (+$((NDATA - FM_ROWS)) more)"
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
# ⛔ the script aims at rows by NUMBER, so the order it aims at is a claim
claim "⛔ the image really has DATA as the root's second entry ($ROOTROWS)" \
  test "$(sed -n 2p "$OUT/root.txt")" = DATA
claim "⛔ ...and v3paint as CMDS's second ($CMDSROWS)" \
  test "$(sed -n 2p "$OUT/cmds.txt")" = v3paint

# --- 1. ⭐ the desktop icon, which was drawn and not clickable ------------
claim "⭐ ONE CLICK ON THE DISK ICON SELECTS IT"                has click 'DESK-ICON arm6309'
claim "⛔ ...AND OPENS NOTHING: three seconds later there is still no window" \
  test "$(field click S0 win)" = no
claim "⭐ AND THE SECOND CLICK OPENS THE FILE MANAGER"          test "$(field click S1 win)" = yes
claim "   and the shell listed the card: DESK-DIR /SD0"        has click 'DESK-DIR /SD0'

# --- 2. the window the toolbox drew ---------------------------------------
claim "⭐ THE CHROME IS WHERE desk.asm PUTS IT - the shadow at $FM_X,$FM_Y, the frame's border at +4, the content panel at +10 ($(get click chrome) of $(get click frames) frames)" \
  test "$(get click chrome)" -ge 1000
# ⚠ THE TAB SAYS WHICH WINDOW IS ACTIVE, and that is what is asked here.
# tbox.asm's TWin paints the tab C.Tab when the FLAGS word's b0 is set and
# C.ITab when it is not, and mktbox.py is where both numbers come from -
# a manager drawn as an inactive window would read $PAL_ITAB here.
claim "⭐ and the tab above it is the ACTIVE one (C.Tab $PAL_TAB, not C.ITab $PAL_ITAB; read $(field click S1 tab))" \
  test "$(field click S1 tab)" = "$PAL_TAB"
claim "⭐ and the title in it is the directory, in the ROM's bold font" \
  test "$(field click S1 title)" = /SD0
claim "the status strip counts the entries" \
  test "$(field click S1 items)" = "${NROOT}_items"

# --- 3. ⭐ THE LIST IS THE REAL DIRECTORY ---------------------------------
claim "⭐ THE LIST IS /SD0's REAL CONTENTS, off the pixels and against os9 dir ($ROOTROWS)" \
  test "$(field click S1 rows)" = "$ROOTROWS"
claim "   ...and nothing is selected in it yet"                test "$(field click S1 sel)" = -

# --- 4. ⭐ entering a directory -------------------------------------------
claim "⭐ ONE CLICK ON A ROW SELECTS IT"                        has click 'DESK-SEL DATA'
claim "   ...it is the row that was clicked"                   test "$(field click S2 sel)" = 1
claim "⛔ ...AND ENTERS NOTHING: the list is still the root's" \
  test "$(field click S2 rows)" = "$ROOTROWS"
claim "⭐ AND THE SECOND CLICK ENTERS IT"                       test "$(field click S3 title)" = /SD0/DATA
claim "⭐ ...and the list is THAT directory's real contents"    test "$(field click S3 rows)" = "$DATAROWS"
claim "   ...and the count is the whole directory, not the page ($NDATA)" \
  test "$(field click S3 items)" = "${NDATA}_items"
claim "   ...and the selection did not survive the change"     test "$(field click S3 sel)" = -

# --- 5. ⭐ scrolling ------------------------------------------------------
claim "⭐ THREE CLICKS ON THE SCROLL BAR'S DOWN ARROW MOVED THE LIST THREE ROWS" \
  test "$(field click S6 rows)" = "$DATAROW3"
claim "   ...and scrolling is not entering: the directory is the same" \
  test "$(field click S6 title)" = /SD0/DATA
claim "⭐ AND THE OTHER ARROW PUTS ONE BACK, which nothing else in this session reaches" \
  test "$(field click S7 rows)" = "$DATAROW2"

# --- 6. ⭐ back up --------------------------------------------------------
claim "⭐ Go > Up WENT TO THE PARENT"                           has click 'DESK-UP /SD0'
claim "⭐ ...and the list is the root's again"                  test "$(field click S9 rows)" = "$ROOTROWS"
claim "   ...and the title with it"                            test "$(field click S9 title)" = /SD0

# --- 6b. ⛔ Go > Close, and the icon that brings the window back ----------
# ⭐ The Go menu's other three items are reached from somewhere else as
# well - Files is what the disk icon carries, Open is the OpenEnt a second
# click on a row reaches, Up is above.  CLOSE IS REACHED FROM NOWHERE ELSE,
# so it is clicked here: a bit the host can ask for and nothing performs is
# exactly what `check:reach` is about, in a menu instead of a macrocell.
claim "⛔ Go > Close TAKES THE WINDOW AWAY"                     test "$(field click S11 win)" = no
claim "   ...and says so on the console"                       has click 'DESK-SHUT'
claim "⭐ AND THE DISK ICON, STILL SELECTED FROM CLICK 0, OPENS IT AGAIN IN ONE CLICK" \
  test "$(field click S12 win)" = yes
claim "⭐ ...on the card's root, listed afresh" \
  test "$(field click S12 title)/$(field click S12 rows)" = "/SD0/$ROOTROWS"

# --- 7. ⭐ opening a program ----------------------------------------------
claim "into CMDS, and its real contents are listed"            test "$(field click S14 rows)" = "$CMDSROWS"
claim "   ...with the directory as the title"                  test "$(field click S14 title)" = /SD0/CMDS
claim "a click selects the program and does not run it"        test "$(field click S15 sel)" = 1
claim "⭐ AND THE SECOND CLICK FORKED IT, by the name in the list" \
  has click 'DESK-RUN v3paint'
claim "⭐ AND v3paint RAN: its own page reached the card's output on $(get click paint) frames" \
  test "$(get click paint)" -ge 20
claim "   ...and it says so itself, on the standard error it inherited"  has click 'V3PAINT-DREW'
claim "⛔ and PAINT'S PICTURE WAS ON THE CARD EXACTLY ONCE ($(get click paintruns) run)" \
  test "$(get click paintruns)" = 1
claim "⭐ and it was THE CLICK ON THE LIST that did it: Paint's first frame ($(get click paint0) s) is after click 16 ($(field click C16 t) s)" \
  gt "$(get click paint0)" "$(field click C16 t)"
claim "⭐ and the DESKTOP came back at $(get click deskback) s, after Paint's last frame at $(get click paint1) s" \
  gt "$(get click deskback)" "$(get click paint1)"
# ⚠ A17, one second before the Quit menu opens - NOT the last frame, which
# is `desk` exited and its window gone with it
claim "⭐ AND SO DID THE WINDOW - out of desk's own table, because the child's DWEnd took the pixels" \
  test "$(field click A17 win)" = yes
claim "⭐ ...with the same directory, the same list and the same selection" \
  test "$(field click A17 title)/$(field click A17 rows)/$(field click A17 sel)" = "/SD0/CMDS/$CMDSROWS/1"
claim "the Quit item ended the program"                        has click 'DESK-BYE'
claim "   and the shell got its prompt back and ran the next command"  has click 'DONE-arm6309'

# --- 8. ⛔ THE NEGATIVE CONTROL -------------------------------------------
# The same ROM, the same card, the same program with the window already up -
# and a mouse that walks over the list and never presses anything.
claim "⛔ the control ran the desktop too"                      has idle 'DESK-READY'
claim "⛔ and it ended on its own iteration bound, not by the clock"  has idle 'DESK-BYE'
claim "⛔ and the script walked the mouse OVER THE LIST ($(get idle restsin) of $(get idle rests) rests inside the list rectangle)" \
  test "$(get idle restsin)" -ge 3
claim "⛔ AND PRESSED NOTHING: no click reached the machine"    test "$(get idle clicks)" = 0
claim "⛔ ...and the window was up the whole run ($(get idle chrome) of $(get idle frames) frames of chrome)" \
  test "$(get idle chrome)" -ge 400
claim "⛔ AND THE LIST HELD EXACTLY ONE PICTURE, over every frame the pointer was off it" \
  test "$(get idle listcrcs)" = 1
claim "⛔ ...and it is still /SD0/DATA's real listing, so a blank window is not what passed it" \
  test "$(field idle SE title)/$(field idle SE rows)" = "/SD0/DATA/$DATAROWS"
claim "⛔ NOTHING WAS EVER SELECTED"                            test "$(field idle SE sel)" = -
claim "⛔ ...nothing was entered: one DESK-DIR, the start-up listing"  count idle 1 'DESK-DIR'
claim "⛔ ...nothing was selected, opened, closed or gone up from" \
  nohas idle 'DESK-SEL\|DESK-UP\|DESK-ICON\|DESK-SHUT'
claim "⛔ ...and no program was launched"                       nohas idle 'DESK-RUN'
claim "⛔ ...and Paint's picture was never on the card"         test "$(get idle paint)" = 0

# --- 9. ⭐ v3trk, the other half of the shared reader ---------------------
claim "⭐ v3trk ran off the card"                               has trk 'TRK-DONE'
claim "⭐ AND ITS LIST OF /SD0/CMDS IS THE SAME REAL CONTENTS, drawn into the same rectangle by the same v3dir.inc" \
  test "$(field trk SE rows)" = "$CMDSROWS"
claim "⛔ ...and it is v3trk and not desk: there is no window round it" \
  test "$(field trk SE win)" = no

echo
echo "      $n claims, $fail failed        (logs in $OUT)"
[ "$fail" -eq 0 ] || exit 1
