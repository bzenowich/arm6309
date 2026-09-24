#!/bin/sh
# ⭐ THE METROIDVANIA SCENE, AND WHAT IT COSTS.
#
#   sh software/mvania/bench/run-v3mv.sh            ~20 min.  OUT=dir, FPS=n, MODES=...
#
# hardware/video3/docs/keyed-copy.md §6.3 says a metroidvania is this card's natural
# genre and that the binding constraint was the per-copy cost, which
# optimizations.md entry 4 took from 698 µs to 344 and entry 5 answered with
# the colour key.  `mvania` is the scene that says what the machine does with
# both: a 1024 × 240 room at ring rows 0-239 with a clean copy at 240-479,
# the view scrolled over it by HSCROLL and VSCROLL with no refill, the hero
# on the card's ONE hardware sprite, and every other actor drawn either by a
# KEYED COPY (full colour, one blit) or by the span writer's sprite WMODE
# (one pass a colour) - and undrawn with a plain copy from the clean page.
#
# ⭐ NINE RUNS, WHICH ARE THE EXPERIMENT.  Each sweeps the actor count 2, 4
# ... 28 and marks every phase of every frame at $FF2E, which the emulator
# timestamps into marks.txt.  `mvania`'s mode is a bit field: b0 one
# rectangle an actor instead of merged, b1 SS.CopyN instead of the card's own
# registers, b2 no restores at all, b3 the scroll by register instead of
# SS.Batch, b4 ⭐ THE KEYED COPY draws the actors instead of the span writer,
# b6 restore and redraw each actor back to back instead of in two phases.
#
#   m81  keyed blits, interleaved, card registers      <- THE SCENE, and the sheets
#   m65  the same with SPRITE-WMODE draws: what the key bought
#   m17  keyed blits, two phases (which is what the merge needs)
#   m1   sprite-WMODE draws, two phases
#   m19  keyed blits through SS.CopyN, the public path
#   m16  keyed blits with the restores MERGED: what the merge is worth
#   m0   sprite-WMODE draws with the restores merged
#   m9   sprite-WMODE, scroll written straight at the card: the floor
#   m4   no restores at all - the control that prices the restores
#   m209 ⭐ the scene again with the scroll through SS.BATCH's records:
#        what the SS.Scroll fast path (mode b7 clear, the default since
#        2026-09-19) is worth, which is 0.77 ms of a 14.3 ms frame
#   m337 ⭐ the scene again with the scroll committed BY THE COMMAND, in
#        the blank its own frame poll already waited for: the OS call out
#        of the frame altogether, which is the other 1.05 ms
#
# ⛔ Its exit code is the answer, and `Error #` on the console fails it.
# ⭐ AND THE CORRECTNESS GATE IS THE VRAM DUMP, not the timings: the scene
# ends by restoring every actor, and the live page must then equal the clean
# page byte for byte.  One pixel left behind by the merge fails it, where a
# timing run would call the same frame a good measurement.
# ⭐ It writes CONTACT SHEETS (OUT/m0/sheet-*.png) and no video: a pass is
# reviewed from the sheets first (CLAUDE.md, and the demo's own rule).
_here=$(cd "$(dirname "$0")" && pwd)   # before any cd: $0 may be relative
set -e
cd "$(dirname "$0")/../../.."
ROOT=$(pwd)
OUT=${OUT:-$(cd "$_here/.." && pwd)/build/v3mv}
FPS=${FPS:-45}
MODES=${MODES:-"81 65 17 1 19 16 0 9 4 209 337"}
SECONDS_OF_MACHINE=${SECONDS_OF_MACHINE:-300}
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  # ⚠ CMDS_EXTRA: since 2026-09-20 the demos are NOT in the ROM disk (they go
  # on an SD card - software/nitros9/mksddisk.sh, software/nitros9/bench/run-v3sd.sh).
  # This bench boots with an empty socket and types `mvania` at /DD, so it
  # asks the recipe for that one command.
  CMDS_EXTRA=mvania sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || {
    tail -20 "$OUT/mkrom.log"; echo "FAIL  the ROM did not build"; exit 1; }
fi
[ -f "$OUT/arm6309_rom.bin" ] || { echo "FAIL  no ROM in $OUT"; exit 1; }
# ⛔ THE CARD IS THE SYSTEM DISK since 2026-09-22 (arm6309 docs/history.md):
# the ROM carries the toolbox and no filesystem, so a session with an EMPTY
# SOCKET does not reach a shell at all.  mkrom.sh writes system.img beside the
# ROM out of the same build, and /DD is that card - which is why the
# `copy /dd/sys/...` lines below still read what SYSROM/$OUT/sys put there.
SDIMG="$OUT/system.img"; export SDIMG
[ -f "$SDIMG" ] || { echo "FAIL  no $SDIMG - mkrom.sh should have built the system card"; exit 1; }
cc -O2 -Wall -I"$ROOT/hardware/audio/refplayer" -o "$OUT/emu" software/emu/machine.c \
   software/emu/cpu6809.c software/emu/hd6309.c "$ROOT/hardware/audio/refplayer/card.c"

STOP=$(printf '\nDONE-arm6309')
FIRST=$(echo $MODES | awk '{print $1}')
fail=0
for m in $MODES; do
  D="$OUT/m$m"
  rm -rf "$D"; mkdir -p "$D"
  # ⚠ CR, not LF (demo-report.md §15.3).  The merge's fixed cost is the third
  # argument: 1393 bytes is 344 µs / 0.247 µs a byte, SS.CopyN's figure.
  printf 'iniz w5\rmvania %d %d %d >/w5\recho DONE-arm6309\r' "$m" "$FPS" "${FIX:-1393}" \
    > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 VRAMDUMP=vram.bin \
     "$OUT/emu" "$OUT/arm6309_rom.bin" . "$SECONDS_OF_MACHINE" > /dev/null 2> emu.log) || true
  tr -d '\000' < "$D/serial.out" | tr -d '\r' > "$D/console.txt"
  grep -q "SERIAL_STOP seen" "$D/emu.log" || {
    echo "FAIL  mode $m did not finish"; tail -5 "$D/emu.log"; fail=1; }
  # ⛔ Strip the colour first: bun and the emulator both write escapes, and
  # `grep '^FAIL'` against a coloured line matches nothing and reads like a
  # pass (CLAUDE.md's seventh trap).
  if grep -n "Error #" "$D/console.txt"; then echo "FAIL  mode $m: a command failed"; fail=1; fi
  if sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -q '^FAIL\|^WILD'; then
    echo "FAIL  mode $m: the emulator objected"
    sed 's/\x1b\[[0-9;]*m//g' "$D/emu.log" | grep -m4 '^FAIL\|^WILD'; fail=1
  fi
  # ⚠ A recording is ~90 KB a frame and a sweep is ~1,400 of them, so four
  # modes is half a gigabyte for three pictures nobody looks at: the sheets
  # come from the FIRST mode and the other three are read for their MARKS.
  # KEEPFRAMES=1 keeps them all.
  [ "$m" = "$FIRST" ] || [ -n "$KEEPFRAMES" ] || rm -f "$D/frames.bin"
done

# ⭐ AND ONE GATE ON THE DRIVER, not on the card: the SAME scene, once with
# the keyed blits issued from the card's own registers and once through
# vidcpy3.asm's SS.CopyN, must put the SAME BYTES in VRAM.  The scene is
# deterministic - every position comes from the iteration count and not from
# the clock - so the two runs are comparable byte for byte, and CP.Key's trip
# through the public path (FromCallerX, the width's bit 15, VcMode, the
# WMODE put back at CpX) is checked by pixels rather than by not crashing.
# ⚠ b5 skips the final Wipe, so what is compared is the scene as drawn.
for m in 49 51; do
  D="$OUT/k$m"
  rm -rf "$D"; mkdir -p "$D"
  printf 'iniz w5\rmvania %d 6 %d >/w5\recho DONE-arm6309\r' "$m" "${FIX:-1393}" > "$D/typed.txt"
  (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
     SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 VRAMDUMP=vram.bin \
     "$OUT/emu" "$OUT/arm6309_rom.bin" . 120 > /dev/null 2> emu.log) || true
  rm -f "$D/frames.bin"
  grep -q "SERIAL_STOP seen" "$D/emu.log" || { echo "FAIL  key gate $m did not finish"; fail=1; }
done
if cmp -s "$OUT/k49/vram.bin" "$OUT/k51/vram.bin"; then
  echo "ok    the keyed scene is the same pixels through SS.CopyN as through the card's registers"
else
  echo "FAIL  the keyed scene differs between vidcpy3's SS.CopyN and the card's registers"
  fail=1
fi

# ⛔ AND THE TEARING GATE, which is the risk this whole path carries: a
# scroll register written while the raster is in the picture TEARS, and
# that is the only reason the commit is the VBL service's at all.  It is
# measurable rather than a matter of opinion - the emulator writes VBLANK's
# rise (V) and each frame's first active line (A) into marks.txt beside the
# marks - so a ROM built with -DBTMARK=1 (defs/armvid.d) marks every commit
# and checkv3mv.py --blank reads each one against the blank it claims to be
# in.  ⭐ WITH A NEGATIVE CONTROL: mode 9 writes the registers wherever the
# raster is, and if ITS writes came out in the blank too the gate would be
# measuring nothing.
# ⚠ The instrument costs ~50 us a frame, so these runs are NOT the
# timings; they are short (FPS=6) and they exist for the claim.
if [ -z "$NOTEAR" ]; then
  BT="$OUT/btmark"
  mkdir -p "$BT"
  AFLAGS_MORE=-DBTMARK=1 sh software/nitros9/mkrom.sh "$BT" > "$BT/mkrom.log" 2>&1 || {
    tail -20 "$BT/mkrom.log"; echo "FAIL  the instrumented ROM did not build"; fail=1; }
  TDIRS=""
  for m in 81 209 337 9; do
    D="$OUT/t$m"
    rm -rf "$D"; mkdir -p "$D"
    printf 'iniz w5\rmvania %d 6 %d >/w5\recho DONE-arm6309\r' "$m" "${FIX:-1393}" > "$D/typed.txt"
    # ⛔ $BT's OWN CARD, not $OUT's.  The instrumented ROM is a different
    # build (-DBTMARK=1 forces the clean), so its modules are different bytes
    # and the card that boots it has to come out of the same make.
    (cd "$D" && SERIAL_IN=typed.txt SERIAL_GATE="DD:" SERIAL_TYPE=60 SERIAL_THINK=700 \
       SERIAL_STOP="$STOP" WILD=1 VIDEO3=1 MARKS=1104 SDIMG="$BT/system.img" \
       "$OUT/emu" "$BT/arm6309_rom.bin" . 120 > /dev/null 2> emu.log) || true
    rm -f "$D/frames.bin"
    grep -q "SERIAL_STOP seen" "$D/emu.log" || { echo "FAIL  tear gate $m did not finish"; fail=1; }
    TDIRS="$TDIRS $D"
  done
  python3 software/mvania/bench/checkv3mv.py --blank $TDIRS || fail=1
fi

# ⭐ One call, with the modes in order: checkv3mv.py makes the contact sheets
# for the FIRST directory it is given and the tables for all of them.
DIRS=""
for m in $MODES; do DIRS="$DIRS $OUT/m$m"; done
python3 software/mvania/bench/checkv3mv.py $DIRS || fail=1
[ "$fail" -eq 0 ] || { echo "FAIL  see above"; exit 1; }
echo "ok    the scene ran in every mode; contact sheets beside $OUT/m$(echo $MODES | awk '{print $1}')"
