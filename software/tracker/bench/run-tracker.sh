#!/bin/sh
# run-tracker.sh - automated playback and verification bench for Tracker (modplay)
#
# Tests Tier 1:
# 1. Runs Python replayer and loader verification (checkmod.py).
# 2. Generates test probes (including 00_notes.mod).
# 3. Builds bootable SD card image with modplay in CMDS and 00_notes.mod in DATA.
# 4. Boots arm6309 emulator with HD6309 CPU and sound card model.
# 5. Executes 'modplay /dd/data/00_notes.mod', verifies startup info, row progression,
#    clean interactive quit ('q'), and audio silence on exit.
_here=$(cd "$(dirname "$0")" && pwd)
set -e
cd "$_here/../../.."
ROOT=$(pwd)
OUT=${OUT:-$_here/../build/bench}
NITROS9DIR=${NITROS9DIR:-$(cd "$ROOT/../nitros9" 2>/dev/null && pwd)}
REC="$NITROS9DIR/recipes/arm6309/l2"
ROM=${ROM:-$ROOT/software/nitros9/build/rom/arm6309_rom.bin}
TOOLS=${TOOLS:-$ROOT/.tools/bin}
export PATH="$TOOLS:$PATH"

mkdir -p "$OUT/data"

# 1. Python model and table verification
echo "=== Step 1: Model, Tables & Binary Verification ==="
python3 "$_here/checkmod.py" || { echo "FAIL  checkmod.py self-test failed"; exit 1; }

# 2. Check or build ROM
if [ ! -f "$ROM" ]; then
  echo "Building NitrOS-9 ROM in $(dirname "$ROM")..."
  sh software/nitros9/mkrom.sh "$(dirname "$ROM")" || { echo "FAIL  mkrom.sh failed"; exit 1; }
fi

# 3. Build modplay command binary in NitrOS-9 recipe
echo "=== Step 2: Building NitrOS-9 modplay command ==="
make -C "$REC" .mods/modplay > "$OUT/build_modplay.log" 2>&1 || {
  cat "$OUT/build_modplay.log"
  echo "FAIL  building .mods/modplay failed"
  exit 1
}

# 4. Prepare data and SD card image
echo "=== Step 3: Preparing SD Card Image ==="
cp "$_here/../build/mod/00_notes.mod" "$OUT/data/00_notes.mod"
printf 'chx /dd/cmds\r' > "$OUT/startup"

STARTUP="$OUT/startup" OUT="$OUT" DATA="$OUT/data" \
  sh software/nitros9/mksyscard.sh "$OUT/sd.img" modplay > "$OUT/mksyscard.log" 2>&1 || {
    cat "$OUT/mksyscard.log"
    echo "FAIL  mksyscard.sh failed"
    exit 1
  }

# 5. Compile host emulator with audio sound card support
echo "=== Step 4: Compiling Host Emulator ==="
cc -O2 -Wall -Ihardware/audio/refplayer -o "$OUT/emu" \
   software/emu/machine.c hardware/cpu/sim/cpu6809.c hardware/cpu/sim/hd6309.c hardware/audio/refplayer/card.c

# 6. Execute in emulator
echo "=== Step 5: Executing modplay in Host Emulator ==="
# Command sequence:
# - Wait for shell prompt (~6s)
# - Run modplay on 00_notes.mod
# - Pause 3 machine seconds (3 x 0x01) to let rows 0..7 play
# - Send 'q' to quit cleanly
# - Pause 1 machine second (0x01)
# - Run echo DONE-arm6309 to trigger SERIAL_STOP
printf 'modplay /dd/data/00_notes.mod\r\001\001\001q\001echo DONE-arm6309\r' > "$OUT/typed.txt"
STOP=$(printf '\nDONE-arm6309')

(cd "$OUT" && \
 SERIAL_IN=typed.txt SERIAL_AT=6 SERIAL_STOP="$STOP" \
 WILD=1 VIDEO3=1 SDIMG="$OUT/sd.img" \
 ./emu "$ROM" . 25 > /dev/null 2> emu.log) || true

tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"

# 7. Verification claims
echo "=== Step 6: Verifying Playback & Teardown Claims ==="
fail=0; n=0
claim() {
  n=$((n+1))
  what=$1; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok    $what"
  else
    echo "FAIL  $what"
    fail=$((fail+1))
  fi
}
has() { grep -q -- "$1" "$OUT/console.txt"; }
has_trace() { grep -q -- "$1" "$OUT/card.trace"; }

claim "modplay command executed without shell errors"       has "Title:"
claim "modplay identified song structure (Patterns: 01)"    has "Patterns: 01"
claim "modplay printed interactive controls"                has "Controls: \[Space\] Pause"
claim "playback advanced across multiple rows"             has "Row: 05"
claim "audio DMA initialized and started"                   has_trace "ADMACON 89"
claim "audio timer programmed for 125 BPM (50 Hz)"          has_trace "TIMER1  37"
claim "audio card silenced on clean exit"                   has_trace "ADMACON 0F"
claim "session returned to shell and completed cleanly"     has "DONE-arm6309"

echo
if [ $fail -eq 0 ]; then
  echo "=== All $n Tracker Tier 1 Bench Verification Claims PASSED ==="
  exit 0
else
  echo "FAIL: $fail of $n claims failed"
  exit 1
fi
