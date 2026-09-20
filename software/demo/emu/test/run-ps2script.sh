#!/bin/sh
# run-ps2script.sh - the bench for PS2_SCRIPT: a timed, semantic keyboard and
# mouse script for the host emulator (software/demo/emu/ps2script.h).
#
#   sh software/demo/emu/test/run-ps2script.sh        (from anywhere)
#   NOBUILD=1 ...    use the NitrOS-9 ROM already in $OUT
#   OUT=dir          overrides /tmp/arm6309-ps2script
#
# ⛔ THE EXIT CODE IS THE ANSWER.  Every line below is a claim.
#
# There is no GUI in this tree yet, so the thing under test is driven against
# what does exist: `ps2tst` (level2/arm6309/cmds/ps2tst.asm) initialises both
# PS/2 ports by ps2.md 7 and 11.2 and echoes every byte it reads back off the
# card.  So the whole path is exercised - the script, the encoder, the
# line-level device at 80 us a bit, the card's '193/'595 and its one-byte
# latch, and a real 6809 polling IOSTAT - and the bytes that come out the far
# end are compared with an encoding computed INDEPENDENTLY, in Python, by
# emu/test/ps2check.py.
#
# ⭐ Two implementations agreeing is evidence; one agreeing with itself is
# not.  And a comparison that cannot fail is worse than none, so each of the
# three comparisons is also run against a deliberately corrupted expectation
# and REQUIRED to catch it.
#
# ⚠ It is in no aggregate: it needs ../nitros9 on its arm6309 branch, like
# software/nitros9/run-emu.sh, and takes about two minutes.
set -e
cd "$(dirname "$0")/../../../.."
ROOT=$(pwd)
OUT=${OUT:-/tmp/arm6309-ps2script}
T=software/demo/emu/test
S=$T/scripts
CHK="python3 $ROOT/$T/ps2check.py"
mkdir -p "$OUT"

if [ -z "$NOBUILD" ]; then
  sh software/nitros9/mkrom.sh "$OUT" > "$OUT/mkrom.log" 2>&1 || { tail -20 "$OUT/mkrom.log"; exit 1; }
fi
ROM="$OUT/arm6309_rom.bin"
[ -f "$ROM" ] || { echo "FAIL  no $ROM"; exit 1; }
cc -O2 -Wall -Iaudio/refplayer -o "$OUT/emu" software/demo/emu/machine.c software/demo/emu/cpu6809.c audio/refplayer/card.c

fail=0; n=0
claim() {  # claim "what" command...
  n=$((n+1)); what=$1; shift
  if "$@" >"$OUT/last.log" 2>&1; then echo "ok    $what"
  else echo "FAIL  $what"; sed 's/^/        /' "$OUT/last.log" | head -6; fail=$((fail+1)); fi
}

# ---------------------------------------------------------------- the encoder
# PS2_SCRIPT_DUMP parses a script and writes the traffic it would produce,
# with its nominal times, without running a machine at all.
dump() { PS2_SCRIPT="$ROOT/$S/$1.ps2" PS2_SCRIPT_DUMP="$OUT/$1.dump" "$OUT/emu"; }
for f in demo keys nomove empty session; do dump $f; done

claim "the worked example encodes to what ps2check.py says, byte for byte and time for time" \
  $CHK match "$S/demo.ps2" "$OUT/demo.dump"
# ⭐ every name the table knows, tapped once: the C table in ps2script.h and
# the Python one in ps2check.py are separate transcriptions of ps2.md 11.1
claim "⭐ and so does EVERY KEY THE TABLE KNOWS - two transcriptions of set 2, code for code" \
  $CHK match "$S/keys.ps2" "$OUT/keys.dump"
claim "...the session the machine is about to be driven with" \
  $CHK match "$S/session.ps2" "$OUT/session.dump"
claim "...the moves-only control" \
  $CHK match "$S/nomove.ps2" "$OUT/nomove.dump"
claim "...and the empty one" \
  $CHK match "$S/empty.ps2" "$OUT/empty.dump"
# ⛔ and the comparison can fail: one byte of the expectation is flipped and
# `match` has to notice.  --mutate inverts the answer itself rather than
# leaving a `!` in the shell, where a missing tool would satisfy it too
claim "⛔ and that comparison is not vacuous: a corrupted byte fails it" \
  $CHK match --mutate "$S/demo.ps2" "$OUT/demo.dump"

# ⚠ the splitting: a PS/2 mouse carries a 9-bit signed delta (ps2.md 11.3),
# so a move of more than 255 in an axis is several packets, and an encoder
# that truncated instead would leave a pointer that drifts and says nothing
claim "every RECORDED packet is inside the 9-bit field, sets no overflow bit, and lands where the script said" \
  $CHK split "$S/demo.ps2" "$OUT/demo.dump"
claim "...including the 900-pixel moves and the walk past zero into negative coordinates" \
  $CHK split "$S/nomove.ps2" "$OUT/nomove.dump"
claim "...and the session's -700, which is three packets" \
  $CHK split "$S/session.ps2" "$OUT/session.dump"

# ⛔ the negative controls
claim "⛔ a script that moves and never clicks produces NO button transition" \
  $CHK nobuttons "$OUT/nomove.dump"
claim "⛔ and an empty script produces no traffic at all" \
  $CHK silent "$OUT/empty.dump"

# ⛔ ...and the parser refuses what it cannot encode, rather than dropping it.
# Both halves are asserted: a non-zero exit AND the message, because an
# emulator that failed to BUILD would also exit non-zero
badkey() {
  printf 'key tap nosuchkey\n' > "$OUT/bad.ps2"
  out=$(PS2_SCRIPT="$OUT/bad.ps2" PS2_SCRIPT_DUMP=- "$OUT/emu" 2>&1); rc=$?
  [ "$rc" -ne 0 ] || { echo "the emulator accepted an unknown key name"; return 1; }
  echo "$out" | grep -q 'unknown key "nosuchkey"' || { echo "exited $rc but said: $out"; return 1; }
}
claim "⛔ an unknown key name is refused by name, not silently dropped" badkey

# `ps2tst N` reads a FIXED count from each device, so the two ports have to
# carry the same number of bytes - and the count comes from here, not from a
# number typed twice
KN=$($CHK bytes "$S/session.ps2" 0)
MN=$($CHK bytes "$S/session.ps2" 1)
claim "the session sends the same number of bytes on both ports ($KN keyboard, $MN mouse)" \
  test "$KN" = "$MN"
N=$KN

# ------------------------------------------------------------------ the machine
# NitrOS-9 boots, the shell runs `ps2tst N`, and the script is timed from the
# gate: the moment the shell echoes the command it was given.
printf 'ps2tst %s\recho DONE-ps2\r' "$N" > "$OUT/typed.txt"
STOP=$(printf '\nDONE-ps2')
(cd "$OUT" && PS2_SCRIPT="$ROOT/$S/session.ps2" PS2_SCRIPT_GATE=ps2tst \
   SERIAL_IN=typed.txt SERIAL_AT=5 SERIAL_STOP="$STOP" WILD=1 \
   ./emu "$ROM" . 90 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/serial.out" | tr -d '\r' > "$OUT/console.txt"

claim "the machine booted and ran ps2tst" grep -q '^kbd:' "$OUT/console.txt"
claim "the run ended at the last command, not by the clock" grep -q 'SERIAL_STOP seen' "$OUT/emu.log"
claim "the CPU never ran through empty RAM (WILD)" sh -c "! grep -q '^WILD' '$OUT/emu.log'"
claim "every event in the script was delivered" grep -q 'all [0-9]* events delivered' "$OUT/emu.log"

claim "ps2.txt records exactly the stream ps2check.py computes, on both ports" \
  $CHK delivered "$S/session.ps2" "$OUT/ps2.txt"
claim "⛔ and that comparison catches a corrupted byte" \
  $CHK delivered --mutate "$S/session.ps2" "$OUT/ps2.txt"

# ⭐ THE ROUND TRIP.  Not what the emulator logged it sent - what the 6809
# read back out of KDATA/MDATA, across the wire and the card, and printed.
claim "⭐ and so does what ps2tst ECHOED off the card: the round trip, through the wire and the one-byte latch" \
  $CHK console "$S/session.ps2" "$OUT/console.txt"
claim "⛔ and THAT comparison catches a corrupted byte too" \
  $CHK console --mutate "$S/session.ps2" "$OUT/console.txt"

# ⭐ the two pointers.  `G` is rebuilt from the bytes the guest READ; `M` is
# where the script thinks it is.  They are compared, not assumed equal
claim "⭐ the pointer rebuilt from the bytes the MACHINE read is where the script said, after a split move into negative X" \
  $CHK pointer "$OUT/ps2.txt"

# the log is joinable to frames.bin and marks.txt: same clock, same shape
claim "ps2.txt's timestamps are picoseconds of machine time and never go backwards" \
  sh -c "awk '{if (\$1+0 < p) exit 1; p = \$1+0} END {exit 0}' '$OUT/ps2.txt'"
claim "...and the last of them is inside the run" \
  sh -c "end=\$(awk '/^end_ps/{print \$2}' '$OUT/sync.txt'); last=\$(grep -v '^#' '$OUT/ps2.txt' | tail -1 | cut -d' ' -f1); [ \"\$last\" -le \"\$end\" ]"

# ------------------------------------------------- ⛔ the control, on the machine
# The same boot, the same ps2tst, and a script with nothing in it: the
# machine must hear silence.  Without this, "the bytes matched" is satisfied
# by a harness that sends the expected bytes whatever the script says.
mkdir -p "$OUT/none"
printf 'ps2tst 3\recho DONE-ps2\r' > "$OUT/none/typed.txt"
(cd "$OUT/none" && PS2_SCRIPT="$ROOT/$S/empty.ps2" \
   SERIAL_IN=typed.txt SERIAL_AT=5 SERIAL_STOP="$STOP" \
   ../emu "$ROM" . 60 > /dev/null 2> emu.log) || true
tr -d '\000' < "$OUT/none/serial.out" | tr -d '\r' > "$OUT/none/console.txt"
claim "⛔ with an empty script the keyboard says only what ps2tst's own commands asked for, then nothing" \
  grep -q '^kbd: FA AA FA AB 83 FA -- -- --$' "$OUT/none/console.txt"
claim "⛔ and the mouse likewise: enabled, reporting, and silent" \
  grep -q '^mouse: FA AA 00 FA FA FA -- -- --$' "$OUT/none/console.txt"
claim "⛔ and ps2.txt has no event in it" $CHK silent "$OUT/none/ps2.txt"

echo "$n claims, $fail failed        (logs in $OUT)"
[ "$fail" -eq 0 ]
