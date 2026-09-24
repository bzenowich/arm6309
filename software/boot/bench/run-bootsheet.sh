#!/bin/sh
# run-bootsheet.sh - the machine booting, from power-on to a file manager, as a
# CONTACT SHEET.
#
#   sh software/boot/bench/run-bootsheet.sh          (from the repository root)
#   OUT=dir   overrides /tmp/arm6309-bootsheet
#
# ⭐ WHAT THIS IS FOR, and it is not a gate.  Every other bench in this tree
# asks whether something is CORRECT.  This one asks what the machine LOOKS
# LIKE doing the thing the owner asked for (software/desk/docs/boot-and-desktop.md): the ROM
# finds the video card, clears the screen, puts up a dialog saying it is
# looking for a disk, changes the icon when it finds a BOOTABLE one, loads
# NitrOS-9 off that card, comes up on the Haiku desktop, and opens a file
# manager on a real directory.
#
# ⛔ SO IT IS ONE RUN, FROM RESET, WITH NOTHING STAGED.  The dialog is not
# drawn for the camera; it is the POST's §10a.  NitrOS-9 is not preloaded; the
# ROM's §10b reads it off block 0's DD.BT.  The desktop is not a recording -
# that is what v3desk was - and the file manager opens because a SCRIPTED MOUSE
# clicked Go > Files.  Every frame on the sheet is a frame the card produced.
#
# ⚠ It is deliberately NOT in any aggregate and has no pass/fail claims beyond
# "the run reached the end and the sheet has tiles".  The claims live in
# run-sdboot.sh (45), run-v3desk.sh (47) and run-v3files.sh (65); this is the
# picture those numbers are about.  Reviewing a demo from a contact sheet, and
# encoding a video only once the look is approved, is this project's rule.
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/bootsheet}
SECS=${SECS:-70}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
NITROS9DIR=${NITROS9DIR:-$ROOT/../nitros9}
REC="$NITROS9DIR/recipes/arm6309/l2"
PATH="$TOOLS:$PATH"; export PATH
mkdir -p "$OUT"

# ---------------------------------------------------------------- the ROM --
# V3=1: the machine's card is video3, and the POST's video sections and its
# dialog only exist under it (hardware/archive/video was retired 2026-09-20).
if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }

# --------------------------------------------------------------- the card --
# ⭐ BOOTABLE, which is the whole difference from every earlier bench: BOOT=
# makes mksddisk.sh run `os9 gen` and stamp LSN 0's signature, so the ROM's
# §10b finds DD.BT and the dialog's icon says FOUND rather than showing the
# Macintosh's question mark.
[ -f "$REC/bootfile" ] || { echo "FAIL  no bootfile in $REC - build the ROM first"; exit 1; }
BOOT="$REC/bootfile" NAME="arm6309" \
  sh software/nitros9/mksddisk.sh "$OUT/sd.img" desk v3paint v3trk monster pinball \
  > "$OUT/mksddisk.log" 2>&1 || {
    cat "$OUT/mksddisk.log"; echo "FAIL  the bootable card did not build"; exit 1; }
cat "$OUT/mksddisk.log"

cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

# ----------------------------------------------------------------- the run --
# ⚠ CR, not LF.  `desk` is forked onto /W3 and prints DESK-READY when its first
# paint is done; PS2_SCRIPT_GATE hangs the mouse script off that, so the clicks
# cannot land before there is a menu bar to click on.
# ⚠ `desk /w3 <ticks>` - the window is an ARGUMENT and the tick bound is
# mandatory (desk.asm's loop is bounded, as CLAUDE.md requires).  `desk >/w3`
# redirects stdout instead, which leaves desk with no window, exits at once,
# and sends the complaint to the window nobody is reading.  That cost a run.
printf 'iniz w3\rchd /sd0\rchx /sd0/cmds\rdesk /w3 %s\r' "${TICKS:-60000}" > "$OUT/typed.txt"
STOP=$(printf '\nDESK-BYE')
( cd "$OUT" && SERIAL_IN=typed.txt SERIAL_GATE="02}" SERIAL_TYPE=60 SERIAL_THINK=700 \
    SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
    PS2_SCRIPT="$ROOT/software/boot/bench/scripts/bootsheet.ps2" PS2_SCRIPT_GATE="DESK-READY" \
    ./emu "$ROM" . "$SECS" > /dev/null 2> emu.log ) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"
sed 's/\x1b\[[0-9;]*m//g' "$OUT/emu.log" > "$OUT/emu.txt"

# --------------------------------------------------------------- the sheet --
fail=0; n=0
claim() { n=$((n+1)); what=$1; shift
  if "$@" >/dev/null 2>&1; then echo "ok    $what"; else echo "FAIL  $what"; fail=$((fail+1)); fi; }

# ⛔ `s` is boot_sd's own answer to "where did OS9Boot come from" - `r` would
# be the ROM disk.  Without this the sheet could show a perfect boot that never
# touched the card, which is the failure run-sdboot.sh's deblocking bug wore.
claim "⭐ NitrOS-9 was read off the CARD, not the ROM disk (boot_sd printed 's')" \
  grep -q "s" "$OUT/console.txt"
claim "the desktop came up and said so"        grep -q "DESK-READY" "$OUT/console.txt"
claim "the file manager listed a directory"    grep -q "DESK-DIR" "$OUT/console.txt"
claim "the CPU never ran through empty RAM"    sh -c "! grep -q '^WILD' '$OUT/emu.txt'"
claim "frames were recorded"                   test -s "$OUT/frames.bin"

# ⭐ THE DIALOG COMES FROM THE OTHER SIMULATOR, and the sheet says so.
# software/emu is a LOGIC model that boots NitrOS-9; it does not run the
# POST's video sections at all - `progress` never leaves $00 and no frame is
# recorded until CoArm sets up a screen, which run-emu.sh's own passing run
# shows too.  The POST's dialog is drawn by the REAL card in Verilog and
# machine_tb writes it out, pixel for pixel, as part of its 52 claims.
# ⛔ Pasting the two together without saying which is which would be a
# staged photograph.  Each tile is labelled with the machine that made it.
DLG=${DLG:-$ROOT/hardware/tools/build}
python3 software/boot/bench/bootsheet.py "$OUT" \
  --dialog "$DLG/screenshot-dialog.ppm" "$DLG/screenshot-dialog-nodisk.ppm" \
  || fail=$((fail + 1))
n=$((n + 1))

echo ""
echo "      $n claims, $fail failed        (sheets in $OUT)"
[ "$fail" -eq 0 ] || exit 1
