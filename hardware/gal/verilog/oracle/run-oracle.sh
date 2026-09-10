#!/bin/sh -e
# The differential oracle: this card against an independent Paula.
#
#   sh gal/verilog/oracle/run-oracle.sh
#
# ⚠ TWO BINARIES, NEVER ONE. Paula.v's licensing is unsettled (its header says
# GPL v3, its repository says CC BY-NC) so nothing here links against it:
# fetch-paula.sh pulls it to a scratch directory, each half is compiled on its
# own, and what is compared is PRINTED OUTPUT. That is cleaner legally and it
# is better testing - no shared harness bug can cancel out in both.
#
# ** WHAT IT COMPARES. The stream of sample bytes each design presents to its
# converter, for the same buffer, LEN, PER and VOL. Not audio: 16 item 36's
# defects were errors in WHICH bytes are played and HOW MANY, which the digital
# path decides on its own.
#
# ** THE STEADY STATE IS THE CLAIM; the first pass is not. Both designs have a
# start-up transient and they are DIFFERENT transients, for reasons that are
# recorded rather than fixed: Paula discards the first word fetched after
# DMACON (an Agnus cycle this harness's Agnus cannot settle - item 36) and this
# card does not strobe its priming byte into the converter (item 39). So the
# comparison drops the first loop and asserts on what repeats.

cd "$(dirname "$0")"
ORACLE="${ORACLE:-/tmp/arm6309-oracle}"
V="verilator --binary --timing"
CARDV="-Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC"

[ -f "$ORACLE/Paula.v" ] || sh ./fetch-paula.sh "$ORACLE"

echo "-- building the card half"
$V $CARDV --top-module card_oracle_tb -I.. \
  ../audio_card.v ../aseq.v ../audio.v card_oracle_tb.sv -o card_oracle_tb >/dev/null

echo "-- building the oracle half (separate binary, nothing linked)"
$V -Wno-lint --top-module paula_oracle_tb \
  "$ORACLE/Paula.v" paula_oracle_tb.sv -o paula_oracle_tb >/dev/null

./obj_dir/card_oracle_tb  > card.out
./obj_dir/paula_oracle_tb > paula.out

# The repeating unit each design settles into, taken from the TAIL so the
# start-up transient is excluded by construction rather than by counting.
#
# ⚠ COMPARED AS A CYCLE, NOT AS A STRING. The two designs reach the same loop
# at different points in it - they have different start-up transients, which is
# the whole reason the first pass is excluded - so a literal comparison of two
# twelve-sample tails reports "04 05 02 03 ..." against "05 02 03 04 ..." and
# calls a match a failure. A rotation test is the honest one: the card's tail
# must appear inside Paula's tail doubled.
steady() {
  grep '^SAMPLE' "$1" | awk '{print $3}' | tail -12 | tr '\n' ' '
}
c=$(steady card.out)
p=$(steady paula.out)

echo
echo "  card   steady state : $c"
echo "  Paula  steady state : $p"
echo

case "$p$p" in
  *"$c"*) echo "ok    ⭐ the card and an independent Paula play the same bytes in the same cyclic order"
          rc=0 ;;
  *)      echo "FAIL  the streams are not rotations of one another"
          rc=1 ;;
esac

echo "      first pass, card  : $(grep '^SAMPLE' card.out  | head -6 | awk '{print $3}' | tr '\n' ' ')"
echo "      first pass, Paula : $(grep '^SAMPLE' paula.out | head -6 | awk '{print $3}' | tr '\n' ' ')"
echo "      ⚠ the first pass is NOT compared - 16 items 36 and 39 say why."
exit $rc
